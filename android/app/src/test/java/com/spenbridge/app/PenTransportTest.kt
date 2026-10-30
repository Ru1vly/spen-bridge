package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class PenTransportTest {
    private val endpoint = ConnectionEndpoint("localhost", 40118, "a".repeat(64), "a".repeat(43))
    private val down = Protocol.Event(3, 0, 4, .5f, .5f, .5f)
    private class Raw : Socket() {
        val closedSignal = CountDownLatch(1)
        override fun close() { closedSignal.countDown(); super.close() }
    }
    private open class Link(val raw: Raw) : ProtocolLink {
        val frames = CopyOnWriteArrayList<ByteArray>()
        var ping: Short = 0
        @Volatile var failHeartbeat = false
        override fun send(packet: ByteArray) {
            if (raw.isClosed) throw IOException("closed")
            frames.add(packet)
            if (packet[4] == Protocol.PKT_PING) ping = ByteBuffer.wrap(packet).order(ByteOrder.LITTLE_ENDIAN).getShort(5)
        }
        override fun receive(timeoutMillis: Int): Protocol.Packet {
            if (failHeartbeat || raw.isClosed) throw IOException("peer closed")
            return Protocol.Packet(Protocol.PKT_PONG, ping, byteArrayOf())
        }
        override fun close() { raw.close() }
        fun eventFrames(): List<ByteArray> = frames.filter { it[4] == Protocol.PKT_EVENT }
    }
    private fun until(predicate: () -> Boolean) {
        repeat(400) { if (predicate()) return; Thread.sleep(5) }
        fail("Transport state did not converge")
    }

    @Test fun noCaptureBeforeUiAcknowledgesAuthenticatedSessionAndNoOfflineReplay() {
        val link = Link(Raw())
        val transport = PenTransport(endpoint, {}, { _, publish -> assertTrue(publish(link.raw)); link }, heartbeatMillis = 20)
        try {
            transport.enqueue(listOf(down))
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            transport.enqueue(listOf(down))
            assertEquals(0, link.eventFrames().size)
            transport.resumeCapture(transport.snapshot.generation)
            transport.enqueue(listOf(down, down.copy(action = Protocol.ACTION_UP, pressure = 0f, buttons = 0)))
            until { link.eventFrames().size == 1 }
            assertEquals(Protocol.HEADER_SIZE + 48, link.eventFrames()[0].size)
        } finally { transport.stop() }
        assertTrue(link.raw.isClosed)
    }

    @Test fun endpointChangeDuringConnectClosesOldSocketAndCannotPublishStaleConnected() {
        val entered = CountDownLatch(1)
        val oldRaw = Raw()
        val newLink = Link(Raw())
        val updates = CopyOnWriteArrayList<PenTransport.Snapshot>()
        val transport = PenTransport(endpoint, { updates.add(it) }, { target, publish ->
            if (target.port == endpoint.port) {
                assertTrue(publish(oldRaw))
                entered.countDown()
                assertTrue(oldRaw.closedSignal.await(2, TimeUnit.SECONDS))
                Link(oldRaw)
            } else { assertTrue(publish(newLink.raw)); newLink }
        })
        try {
            transport.start()
            assertTrue(entered.await(2, TimeUnit.SECONDS))
            val oldGeneration = transport.snapshot.generation
            transport.enqueue(listOf(down))
            transport.updateEndpoint(endpoint.copy(port = 40119))
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            assertTrue(oldRaw.isClosed)
            assertFalse(updates.any { it.state == PenTransport.State.CONNECTED && it.generation == oldGeneration })
            assertTrue(newLink.eventFrames().isEmpty())
        } finally { transport.stop() }
    }

    @Test fun stopCancelsAnInFlightConnectAndJoinsWorker() {
        val entered = CountDownLatch(1)
        val raw = Raw()
        val transport = PenTransport(endpoint, {}, { _, publish ->
            assertTrue(publish(raw)); entered.countDown()
            raw.closedSignal.await(2, TimeUnit.SECONDS)
            throw IOException("cancelled")
        })
        transport.start()
        assertTrue(entered.await(2, TimeUnit.SECONDS))
        transport.stop()
        assertTrue(raw.isClosed)
        assertEquals(PenTransport.State.DISCONNECTED, transport.snapshot.state)
    }

    @Test fun heartbeatFailureRemovesConnectedState() {
        val link = Link(Raw())
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(link.raw); link },
                                     retryMillis = 5000, heartbeatMillis = 10)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            link.failHeartbeat = true
            until { transport.snapshot.state == PenTransport.State.ERROR && link.raw.isClosed }
            assertTrue(link.raw.isClosed)
        } finally { transport.stop() }
    }

    @Test fun watchdogClosesBlockedWriterWithoutNeedingMorePenEvents() {
        val entered = CountDownLatch(1)
        val raw = Raw()
        val link = object : Link(raw) {
            override fun send(packet: ByteArray) {
                if (packet[4] == Protocol.PKT_EVENT) {
                    entered.countDown()
                    raw.closedSignal.await(2, TimeUnit.SECONDS)
                    throw IOException("write cancelled")
                }
                super.send(packet)
            }
        }
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(raw); link },
                                     retryMillis = 5000, stallMillis = 100)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            transport.resumeCapture(transport.snapshot.generation)
            transport.enqueue(listOf(down))
            assertTrue(entered.await(2, TimeUnit.SECONDS))
            until { transport.snapshot.state == PenTransport.State.ERROR }
            assertTrue(raw.isClosed)
        } finally { transport.stop() }
    }

    @Test fun missingPairingCannotAttemptNetworkConnection() {
        var attempts = 0
        val transport = PenTransport(endpoint.copy(code = ""), {}, { _, _ -> attempts++; throw IOException() })
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.PAIRING_REQUIRED }
            assertEquals(0, attempts)
        } finally { transport.stop() }
    }
}
