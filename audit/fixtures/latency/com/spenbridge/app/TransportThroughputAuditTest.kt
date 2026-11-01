package com.spenbridge.app

import org.junit.Test
import org.junit.Assert.*
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.locks.LockSupport
import kotlin.math.roundToInt

/** Capacity/latency observation of the actual sender, excluding hardware/network. */
class TransportThroughputAuditTest {
    @Test fun productionSenderSustainsOneThousandPacketsWhilePongIsDelayed() {
        val rows = listOf(1, 5).map { batchSize ->
            val created = ConcurrentHashMap<Int,Long>()
            val delays = ConcurrentLinkedQueue<Double>()
            val packetCount = AtomicInteger()
            val errors = AtomicInteger()
            val ready = CountDownLatch(1)
            var ping: Short = 0
            val link = object : ProtocolLink {
                override fun send(packet: ByteArray) {
                    if (packet[4] == Protocol.PKT_PING) ping = ByteBuffer.wrap(packet).order(ByteOrder.LITTLE_ENDIAN).getShort(5)
                    if (packet[4] == Protocol.PKT_EVENT) {
                        packetCount.incrementAndGet()
                        val now = System.nanoTime()
                        val frame = ByteBuffer.wrap(packet).order(ByteOrder.LITTLE_ENDIAN)
                        for (offset in Protocol.HEADER_SIZE until packet.size step Protocol.EVENT_RECORD_SIZE) {
                            val id = (frame.getFloat(offset + 4) * 100000f).roundToInt()
                            val start = created.remove(id) ?: error("Lost sample identity")
                            delays.add((now-start) / 1000.0)
                        }
                    }
                }
                override fun receive(timeoutMillis: Int): Protocol.Packet {
                    Thread.sleep(150)
                    return Protocol.Packet(Protocol.PKT_PONG,ping,byteArrayOf())
                }
                override fun close() {}
            }
            lateinit var tx: PenTransport
            tx = PenTransport(ConnectionEndpoint("desktop.example.test",40118,"0".repeat(64),"A".repeat(43)),
                observer = {
                    if (it.state == PenTransport.State.CONNECTED) { tx.resumeCapture(it.generation); ready.countDown() }
                    if (it.state == PenTransport.State.ERROR) errors.incrementAndGet()
                }, openLink = { _, _ -> link })
            try {
                tx.start();assertTrue(ready.await(2,TimeUnit.SECONDS))
                val start = System.nanoTime()
                var id = 0
                for (packet in 0 until 3000) {
                    val deadline = start + packet * 1_000_000L
                    while (true) {
                        val remaining = deadline - System.nanoTime()
                        if (remaining <= 0) break
                        LockSupport.parkNanos(remaining)
                    }
                    val events = List(batchSize) {
                        val sample = ++id
                        created[sample] = System.nanoTime()
                        Protocol.Event(Protocol.ACTION_MOVE,Protocol.TOOL_STYLUS,Protocol.BUTTON_TOUCH,sample / 100000f,.5f,.7f)
                    }
                    tx.enqueue(events)
                }
                val elapsed = (System.nanoTime()-start)/1e9
                val drainDeadline = System.nanoTime()+TimeUnit.SECONDS.toNanos(2)
                while (delays.size < id && System.nanoTime()<drainDeadline) Thread.sleep(1)
                assertEquals("Every offered sample must be transmitted",id,delays.size)
                assertEquals(0,errors.get())
                assertEquals(3000,packetCount.get())
                val sorted = delays.sorted()
                fun pct(p:Double)=sorted[((sorted.size-1)*p).roundToInt()]
                """{"target_packets_per_second":1000,"batch_size":$batchSize,"events":$id,"packets":${packetCount.get()},"elapsed_seconds":$elapsed,"actual_packets_per_second":${3000/elapsed},"pong_delay_ms":150,"p50_queue_us":${pct(.5)},"p95_queue_us":${pct(.95)},"p99_queue_us":${pct(.99)},"max_queue_us":${pct(1.0)},"errors":${errors.get()}}"""
            } finally { tx.stop() }
        }
        File(System.getProperty("spen.audit.output")).resolveSibling("android-throughput.json")
            .writeText("""{"scope":"JVM production sender and queue, simulated link, excludes physical pen/USB/network/OS injection","rows":[${rows.joinToString(",")}]}"""+"\n")
    }
}
