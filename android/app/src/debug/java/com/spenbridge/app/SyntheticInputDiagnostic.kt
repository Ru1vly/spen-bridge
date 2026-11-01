package com.spenbridge.app

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.locks.LockSupport

/** Explicit shell-invoked production sender test, never creates MotionEvents. */
object SyntheticInputDiagnostic {
    private val running = AtomicBoolean(false)
    @Volatile private var state = "idle"

    fun status(): String = state

    fun start(context: Context, path: String): String {
        check(running.compareAndSet(false, true)) { "A synthetic test is already active" }
        try {
            val configFile = File(path).canonicalFile
            check(configFile.path.startsWith(context.cacheDir.canonicalPath + File.separator)) { "Private cache config required" }
            check(configFile.length() in 1..2048) { "Invalid config size" }
            val config = JSONObject(configFile.readText())
            val port = config.getInt("port")
            check(port in 1..65535)
            val packets = config.optInt("packets", 5000)
            val rate = config.optInt("rate", 1000)
            check(packets in 100..10000 && rate in 100..3000 && packets * 1000L / rate <= 15000)
            val endpoint = ConnectionEndpoint("127.0.0.1", port, config.getString("fingerprint"), config.getString("code"))
            check(endpoint.isPaired())
            state = "running"
            Thread({ run(endpoint, packets, rate) }, "SPenSyntheticSource").apply { isDaemon = true; start() }
        } catch (error: Exception) { running.set(false); throw error }
        return state
    }

    private fun run(endpoint: ConnectionEndpoint, packets: Int, rate: Int) {
        val ready = CountDownLatch(1)
        lateinit var transport: PenTransport
        transport = PenTransport(endpoint, { update ->
            if (update.state == PenTransport.State.CONNECTED) {
                transport.resumeCapture(update.generation)
                ready.countDown()
            }
        })
        try {
            transport.start()
            check(ready.await(5, TimeUnit.SECONDS))
            val started = System.nanoTime()
            val period = 1000000000L / rate
            for (index in 0 until packets) {
                val deadline = started + index * period
                while (true) {
                    val remaining = deadline - System.nanoTime()
                    if (remaining <= 0) break
                    LockSupport.parkNanos(remaining)
                }
                val now = System.nanoTime()
                InputTrace.synthetic(now, index)
                transport.enqueue(listOf(Protocol.Event(Protocol.ACTION_HOVER_MOVE, Protocol.TOOL_STYLUS, 0,
                    index / 20000f, .5f, 0f)))
            }
            // The receiver independently checks complete delivery; this pause
            // only permits the last pending write to drain, not offline replay.
            Thread.sleep(300)
            state = "complete:$packets"
        } catch (_: Exception) { state = "error:synthetic" }
        finally {
            try { transport.stop() } catch (_: Exception) { state = "error:cleanup" }
            running.set(false)
        }
    }
}
