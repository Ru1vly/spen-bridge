package com.spenbridge.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors
import java.util.zip.CRC32

/** Opt-in, debug-only tracing in the normal application; no process restarts. */
object InputTrace {
    private class Capture(val context: Context, val name: String) {
        val buffer = TimingTraceBuffer(200000)
        val crc = CRC32()
        val began = System.nanoTime()
        var timeout: Runnable? = null
    }
    @Volatile private var current: Capture? = null
    @Volatile private var lastStatus = "idle"
    private val handler by lazy { Handler(Looper.getMainLooper()) }
    private val exporter = Executors.newSingleThreadExecutor { work -> Thread(work, "SPenTraceExport").apply { isDaemon = true } }
    val enabled: Boolean get() = current != null

    @Synchronized fun start(context: Context, seconds: Int): String {
        require(seconds in 1..60)
        check(current == null && !lastStatus.startsWith("exporting:")) { "A capture/export is already active" }
        val name = "input-trace-${System.currentTimeMillis()}.bin"
        val capture = Capture(context.applicationContext, name)
        current = capture
        lastStatus = "recording:$name"
        capture.timeout = Runnable { if (current === capture) stop() }
        handler.postDelayed(checkNotNull(capture.timeout), seconds * 1000L)
        return lastStatus
    }

    @Synchronized fun stop(): String {
        val capture = current ?: return lastStatus
        current = null
        capture.timeout?.let { handler.removeCallbacks(it) }
        capture.timeout = null
        capture.buffer.freeze()
        val ended = System.nanoTime()
        lastStatus = "exporting:${capture.name}"
        exporter.execute {
            val temporary = File(capture.context.filesDir, capture.name + ".tmp")
            try {
                val header = JSONObject().put("version", 1).put("side", "android")
                    .put("clock", "CLOCK_MONOTONIC").put("record_bytes", 64)
                    .put("started_ns", capture.began).put("ended_ns", ended)
                    .put("records", capture.buffer.stored).put("seen", capture.buffer.seen)
                    .put("overflow", capture.buffer.seen - capture.buffer.stored).toString().toByteArray(Charsets.UTF_8)
                DataOutputStream(BufferedOutputStream(FileOutputStream(temporary), 65536)).use { output ->
                    output.writeInt(header.size); output.write(header); capture.buffer.writeTo(output)
                }
                check(temporary.renameTo(File(capture.context.filesDir, capture.name))) { "Trace export failed" }
                lastStatus = "ready:${capture.name}"
            } catch (_: Exception) {
                temporary.delete()
                lastStatus = "error:export"
            }
        }
        return lastStatus
    }

    fun status(): String = lastStatus

    fun sample(sourceNanos: Long, callbackNanos: Long, precise: Boolean, action: Byte) {
        val capture = current ?: return
        capture.buffer.append(1, if (precise) 1 else 0, action.toLong(), 1,
            sourceNanos, callbackNanos, 0, 0)
    }

    fun rejected(oldestMillis: Long, currentMillis: Long, callback: Long, count: Int, reason: Int) {
        val capture = current ?: return
        capture.buffer.append(8, reason.toLong(), -1, count.toLong(), oldestMillis * 1000000L, callback, currentMillis * 1000000L, 0)
    }

    fun queueReset(session: Long, count: Int, reason: Int) {
        val capture = current ?: return
        capture.buffer.append(9, session, reason.toLong(), count.toLong(), System.nanoTime(), 0, 0, 0)
    }

    fun state(session: Long, state: Int) {
        val capture = current ?: return
        capture.buffer.append(10, session, state.toLong(), 0, System.nanoTime(), 0, 0, 0)
    }

    fun synthetic(now: Long, index: Int) {
        val capture = current ?: return
        capture.buffer.append(7, 0, index.toLong(), 1, now, now, 0, 0)
    }

    fun queued(session: Long, count: Int) {
        val capture = current ?: return
        capture.buffer.append(2, session, -1, count.toLong(), System.nanoTime(), 0, 0, 0)
    }

    fun heartbeat(session: Long, sequence: Short, began: Long, written: Long, received: Long) {
        val capture = current ?: return
        capture.buffer.append(4, session, sequence.toLong() and 65535, 0, began, written, received, 0)
    }

    fun packet(session: Long, sequence: Short, count: Int, bytes: ByteArray, size: Int,
               created: Long, began: Long, ended: Long) {
        val capture = current ?: return
        synchronized(capture.buffer) {
            capture.crc.reset()
            capture.crc.update(bytes, Protocol.HEADER_SIZE, size - Protocol.HEADER_SIZE)
            capture.buffer.append(3, session, sequence.toLong() and 65535, count.toLong(),
                created, began, ended, capture.crc.value)
        }
    }
}
