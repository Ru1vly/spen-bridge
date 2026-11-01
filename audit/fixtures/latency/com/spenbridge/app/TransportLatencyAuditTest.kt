package com.spenbridge.app

import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.roundToInt

/** Audit observation only: production transport/queue with a controlled PONG delay.
 * No Android sensor, real network, server or OS input device is used here.
 */
class TransportLatencyAuditTest {
    @Test fun measureQueueDelayWhileWaitingForHeartbeat() {
        val rows = listOf(0L, 10L, 60L, 150L).map { delay ->
            val created = ConcurrentHashMap<Int, Long>()
            val latencies = ConcurrentLinkedQueue<Double>()
            val errors = AtomicInteger()
            val connections = AtomicInteger()
            val ready = CountDownLatch(1)
            lateinit var tx: PenTransport
            class Link : ProtocolLink {
                var ping: Short = 0
                override fun send(packet: ByteArray) {
                    val now = System.nanoTime()
                    val frame = ByteBuffer.wrap(packet).order(ByteOrder.LITTLE_ENDIAN)
                    when (packet[4]) {
                        Protocol.PKT_PING -> ping = frame.getShort(5)
                        Protocol.PKT_EVENT -> {
                            var offset = Protocol.HEADER_SIZE
                            while (offset + Protocol.EVENT_RECORD_SIZE <= packet.size) {
                                val id = (frame.getFloat(offset + 4) * 10000f).roundToInt()
                                created.remove(id)?.let { latencies.add((now-it) / 1_000_000.0) }
                                offset += Protocol.EVENT_RECORD_SIZE
                            }
                        }
                    }
                }
                override fun receive(timeoutMillis: Int): Protocol.Packet {
                    if (delay > 0) Thread.sleep(delay)
                    return Protocol.Packet(Protocol.PKT_PONG, ping, byteArrayOf())
                }
                override fun close() {}
            }
            tx = PenTransport(ConnectionEndpoint("desktop.example.test", 40118, "0".repeat(64), "A".repeat(43)),
                observer = { state ->
                    if (state.state == PenTransport.State.CONNECTED) {
                        connections.incrementAndGet()
                        tx.resumeCapture(state.generation)
                        ready.countDown()
                    }
                    if (state.state == PenTransport.State.ERROR) errors.incrementAndGet()
                }, openLink = { _, _ -> Link() })
            tx.start()
            check(ready.await(2, TimeUnit.SECONDS))
            val began = System.nanoTime()
            var produced = 0
            // 500Hz offered for 2.6 seconds; includes multiple one-second heartbeats.
            while (System.nanoTime()-began < TimeUnit.MILLISECONDS.toNanos(2600)) {
                val id = ++produced
                created[id] = System.nanoTime()
                tx.enqueue(listOf(Protocol.Event(Protocol.ACTION_MOVE, Protocol.TOOL_STYLUS,
                    Protocol.BUTTON_TOUCH, id / 10000f, .5f, .5f)))
                Thread.sleep(2)
            }
            Thread.sleep(250)
            val stopStart = System.nanoTime()
            tx.stop()
            val stopMs = (System.nanoTime()-stopStart) / 1_000_000.0
            val sorted = latencies.sorted()
            fun percentile(p: Double): String = if (sorted.isEmpty()) "null" else
                sorted[((sorted.size-1)*p).roundToInt()].toString()
            """{"pong_delay_ms":$delay,"produced":$produced,"sent":${sorted.size},"error_states":${errors.get()},"connections":${connections.get()},"p50_ms":${percentile(.5)},"p95_ms":${percentile(.95)},"p99_ms":${percentile(.99)},"max_ms":${percentile(1.0)},"stop_ms":$stopMs}"""
        }
        val json = """{"scope":"JVM production PenTransport + SessionBuffer, fake link with controlled PONG delay; excludes hardware and real network","rows":[${rows.joinToString(",")}]}"""
        File(System.getProperty("spen.audit.output")).writeText(json+"\n")
        println(json)
    }
}
