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
            until { transport.snapshot.state == PenTransport.State.COOLDOWN && link.raw.isClosed }
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
            until { transport.snapshot.state == PenTransport.State.COOLDOWN }
            assertTrue(raw.isClosed)
        } finally { transport.stop() }
    }

    @Test fun usbIsAlwaysFirstWithoutOverwritingTheWifiAddress() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val attempted = CopyOnWriteArrayList<String>()
        val link = Link(Raw())
        val transport = PenTransport(wifi, {}, { target, publish ->
            attempted.add(target.host)
            assertTrue(publish(link.raw)); link
        })
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            assertEquals(listOf("127.0.0.1"), attempted.toList())
            assertEquals(PenTransport.Mode.USB, transport.snapshot.mode)
            assertEquals(wifi, transport.endpoint())
        } finally { transport.stop() }
    }

    @Test fun failedUsbImmediatelyFallsBackToWifiAndReportsActualMode() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val attempted = CopyOnWriteArrayList<String>()
        val link = Link(Raw())
        val start = System.nanoTime()
        val transport = PenTransport(wifi, {}, { target, publish ->
            attempted.add(target.host)
            if (target.isLoopback()) throw IOException("USB unavailable")
            assertTrue(publish(link.raw)); link
        }, retryMillis = 5000)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            assertTrue(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start) < 2000)
            assertEquals(listOf("127.0.0.1", wifi.host), attempted.toList())
            assertEquals(PenTransport.Mode.WIFI, transport.snapshot.mode)
        } finally { transport.stop() }
    }

    @Test fun bothFailuresWaitFiveSecondsThenRestartWithUsb() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val attempted = CopyOnWriteArrayList<Pair<String, Long>>()
        val second = CountDownLatch(1)
        val third = CountDownLatch(1)
        val transport = PenTransport(wifi, {}, { target, _ ->
            attempted.add(target.host to System.nanoTime())
            if (attempted.size == 2) second.countDown()
            if (attempted.size == 3) third.countDown()
            throw IOException("unreachable")
        })
        try {
            transport.start()
            assertTrue(second.await(2, TimeUnit.SECONDS))
            until { transport.snapshot.state == PenTransport.State.COOLDOWN }
            assertEquals(listOf("127.0.0.1", wifi.host), attempted.map { it.first })
            assertFalse(third.await(4500, TimeUnit.MILLISECONDS))
            assertTrue(third.await(2, TimeUnit.SECONDS))
            assertEquals("127.0.0.1", attempted[2].first)
            assertTrue(TimeUnit.NANOSECONDS.toMillis(attempted[2].second - attempted[1].second) >= 4900)
        } finally { transport.stop() }
    }

    @Test fun lostUsbSessionFallsBackWithFreshCaptureAndNoReplayedInput() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val usbLink = Link(Raw())
        val wifiLink = Link(Raw())
        val transport = PenTransport(wifi, {}, { target, publish ->
            val link = if (target.isLoopback()) usbLink else wifiLink
            assertTrue(publish(link.raw)); link
        }, heartbeatMillis = 10)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            val usbGeneration = transport.snapshot.generation
            transport.resumeCapture(usbGeneration)
            usbLink.failHeartbeat = true
            until { transport.snapshot.state == PenTransport.State.CONNECTED && transport.snapshot.mode == PenTransport.Mode.WIFI }
            assertTrue(usbLink.raw.isClosed)
            assertNotEquals(usbGeneration, transport.snapshot.generation)
            transport.enqueue(listOf(down))
            assertTrue(wifiLink.eventFrames().isEmpty())
            transport.resumeCapture(transport.snapshot.generation)
            transport.enqueue(listOf(down))
            until { wifiLink.eventFrames().size == 1 }
        } finally { transport.stop() }
    }

    @Test fun endpointChangeInterruptsCooldownAndStartsWithUsb() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val newLink = Link(Raw())
        val attempted = CopyOnWriteArrayList<ConnectionEndpoint>()
        val transport = PenTransport(wifi, {}, { target, publish ->
            attempted.add(target)
            if (target.port == 40118) throw IOException("unreachable")
            assertTrue(publish(newLink.raw)); newLink
        })
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.COOLDOWN }
            transport.updateEndpoint(wifi.copy(host = "192.168.1.16", port = 40119))
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            assertEquals("127.0.0.1", attempted.last().host)
            assertEquals(40119, attempted.last().port)
            assertEquals(PenTransport.Mode.USB, transport.snapshot.mode)
        } finally { transport.stop() }
    }

    @Test fun repeatedForegroundStopsContainInterruptedWatchdogCleanup() {
        val entered = java.util.concurrent.ArrayBlockingQueue<Raw>(1)
        val uncaught = CopyOnWriteArrayList<Throwable>()
        val transport = PenTransport(endpoint, {
            if (Thread.currentThread().name == "SPenTransport") {
                Thread.currentThread().uncaughtExceptionHandler = Thread.UncaughtExceptionHandler { _, error -> uncaught.add(error) }
            }
        }, { _, publish ->
            val raw = Raw()
            assertTrue(publish(raw))
            entered.put(raw)
            try { raw.closedSignal.await(2, TimeUnit.SECONDS) }
            catch (_: InterruptedException) { Thread.currentThread().interrupt() }
            throw IOException("foreground stopped")
        })
        repeat(20) {
            transport.start()
            val raw = entered.poll(2, TimeUnit.SECONDS)
            assertNotNull(raw)
            transport.stop()
            assertTrue(raw.isClosed)
            assertEquals(PenTransport.State.DISCONNECTED, transport.snapshot.state)
        }
        assertTrue("Uncaught cleanup failures: $uncaught", uncaught.isEmpty())
    }

    @Test fun idleWifiUpgradesOnlyAfterAuthenticatedUsbReadinessAndFreshCapture() {
        val wifi = endpoint.copy(host = "192.168.1.15")
        val wifiLink = Link(Raw())
        val usbLink = Link(Raw())
        val attempts = CopyOnWriteArrayList<String>()
        val transport = PenTransport(wifi, {}, { target, publish ->
            attempts.add(target.host)
            if (target.isLoopback() && attempts.size == 1) throw IOException("no cable yet")
            val link = if (target.isLoopback()) usbLink else wifiLink
            if (target.isLoopback()) assertTrue(wifiLink.raw.isClosed)
            assertTrue(publish(link.raw)); link
        }, heartbeatMillis = 10, usbProbeMillis = 20, idleMillis = 40,
            probeUsb = { _, publish -> val raw = Raw(); assertTrue(publish(raw)); raw.close(); true })
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED && transport.snapshot.mode == PenTransport.Mode.WIFI }
            val old = transport.snapshot.generation
            transport.resumeCapture(old)
            until { transport.snapshot.state == PenTransport.State.CONNECTED && transport.snapshot.mode == PenTransport.Mode.USB }
            assertNotEquals(old, transport.snapshot.generation)
            assertEquals(listOf("127.0.0.1", wifi.host, "127.0.0.1"), attempts.toList())
            transport.enqueue(listOf(down))
            assertTrue(usbLink.eventFrames().isEmpty())
            transport.resumeCapture(transport.snapshot.generation)
            transport.enqueue(listOf(down))
            until { usbLink.eventFrames().size == 1 }
        } finally { transport.stop() }
    }

    @Test fun stationaryContactAndHeldBarrelBlockUsbUpgradeUntilReleased() {
        val wifiLink = Link(Raw())
        val usbLink = Link(Raw())
        var opens = 0
        val probes = java.util.concurrent.atomic.AtomicInteger()
        val transport = PenTransport(endpoint.copy(host = "192.168.1.15"), {}, { target, publish ->
            if (target.isLoopback() && opens++ == 0) throw IOException("no cable")
            val link = if (target.isLoopback()) usbLink else wifiLink
            publish(link.raw); link
        }, heartbeatMillis = 10, usbProbeMillis = 20, idleMillis = 40,
            probeUsb = { _, _ -> probes.incrementAndGet(); true })
        try {
            transport.start()
            until { transport.snapshot.mode == PenTransport.Mode.WIFI && transport.snapshot.state == PenTransport.State.CONNECTED }
            val session = transport.snapshot.generation
            transport.resumeCapture(session)
            transport.enqueue(listOf(down))
            until { wifiLink.eventFrames().isNotEmpty() }
            transport.resumeCapture(session) // A repeated acknowledgement must not erase held contact.
            Thread.sleep(140)
            assertEquals(PenTransport.Mode.WIFI, transport.snapshot.mode)
            assertEquals(0, probes.get())
            transport.enqueue(listOf(down.copy(action = Protocol.ACTION_UP, pressure = 0f, buttons = Protocol.BUTTON_STYLUS)))
            Thread.sleep(140)
            assertEquals(PenTransport.Mode.WIFI, transport.snapshot.mode)
            assertEquals(0, probes.get())
            transport.enqueue(listOf(down.copy(action = Protocol.ACTION_HOVER_EXIT, pressure = 0f, buttons = 0)))
            until { transport.snapshot.mode == PenTransport.Mode.USB && transport.snapshot.state == PenTransport.State.CONNECTED }
            assertTrue(wifiLink.raw.isClosed)
        } finally { transport.stop() }
    }

    @Test fun inputContinuesDuringReadinessProbeAndNewContactDefersHandover() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val wifiLink = Link(Raw())
        val usbLink = Link(Raw())
        var opens = 0
        val transport = PenTransport(endpoint.copy(host = "192.168.1.15"), {}, { target, publish ->
            if (target.isLoopback() && opens++ == 0) throw IOException("no cable")
            val link = if (target.isLoopback()) usbLink else wifiLink
            publish(link.raw); link
        }, heartbeatMillis = 10, usbProbeMillis = 20, idleMillis = 40, probeUsb = { _, publish ->
            val raw = Raw(); assertTrue(publish(raw)); entered.countDown()
            release.await(1, TimeUnit.SECONDS); raw.close(); true
        })
        try {
            transport.start()
            until { transport.snapshot.mode == PenTransport.Mode.WIFI && transport.snapshot.state == PenTransport.State.CONNECTED }
            transport.resumeCapture(transport.snapshot.generation)
            assertTrue(entered.await(1, TimeUnit.SECONDS))
            transport.enqueue(listOf(down))
            until { wifiLink.eventFrames().size == 1 }
            release.countDown()
            Thread.sleep(120)
            assertEquals(PenTransport.Mode.WIFI, transport.snapshot.mode)
            transport.enqueue(listOf(down.copy(action = Protocol.ACTION_UP, pressure = 0f, buttons = 0)))
            until { transport.snapshot.mode == PenTransport.Mode.USB && transport.snapshot.state == PenTransport.State.CONNECTED }
        } finally { release.countDown(); transport.stop() }
    }

    @Test fun unavailableUsbProbeLeavesWifiOwnerAndInputUntouched() {
        val wifiLink = Link(Raw())
        val probes = java.util.concurrent.atomic.AtomicInteger()
        val transport = PenTransport(endpoint.copy(host = "192.168.1.15"), {}, { target, publish ->
            if (target.isLoopback()) throw IOException("no cable")
            publish(wifiLink.raw); wifiLink
        }, heartbeatMillis = 10, usbProbeMillis = 20, idleMillis = 20,
            probeUsb = { _, _ -> probes.incrementAndGet(); throw IOException("not ready") })
        try {
            transport.start()
            until { transport.snapshot.mode == PenTransport.Mode.WIFI && transport.snapshot.state == PenTransport.State.CONNECTED }
            val session = transport.snapshot.generation
            transport.resumeCapture(session)
            until { probes.get() >= 3 }
            assertEquals(session, transport.snapshot.generation)
            assertFalse(wifiLink.raw.isClosed)
            transport.enqueue(listOf(down))
            until { wifiLink.eventFrames().size == 1 }
        } finally { transport.stop() }
    }

    @Test fun stopClosesAndJoinsAnInFlightUsbProbe() {
        val entered = CountDownLatch(1)
        val probeRaw = Raw()
        val wifiLink = Link(Raw())
        val transport = PenTransport(endpoint.copy(host = "192.168.1.15"), {}, { target, publish ->
            if (target.isLoopback()) throw IOException("no cable")
            publish(wifiLink.raw); wifiLink
        }, heartbeatMillis = 10, usbProbeMillis = 20, idleMillis = 20, probeUsb = { _, publish ->
            publish(probeRaw); entered.countDown()
            probeRaw.closedSignal.await(2, TimeUnit.SECONDS); false
        })
        transport.start()
        until { transport.snapshot.mode == PenTransport.Mode.WIFI && transport.snapshot.state == PenTransport.State.CONNECTED }
        transport.resumeCapture(transport.snapshot.generation)
        assertTrue(entered.await(1, TimeUnit.SECONDS))
        transport.stop()
        assertTrue(probeRaw.isClosed)
        assertTrue(wifiLink.raw.isClosed)
        assertEquals(PenTransport.State.DISCONNECTED, transport.snapshot.state)
    }

    @Test fun delayedPongDoesNotBlockPenOrReleaseFrames() {
        val receiving = CountDownLatch(1)
        val releasePong = CountDownLatch(1)
        val link = object : Link(Raw()) {
            override fun receive(timeoutMillis: Int): Protocol.Packet {
                receiving.countDown()
                assertTrue(releasePong.await(2, TimeUnit.SECONDS))
                return super.receive(timeoutMillis)
            }
        }
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(link.raw); link })
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            transport.resumeCapture(transport.snapshot.generation)
            assertTrue(receiving.await(1, TimeUnit.SECONDS))
            transport.enqueue(listOf(down))
            until { link.eventFrames().size == 1 }
            // The peer has not acknowledged PING, but input and its release
            // must still be delivered by the independently ordered writer.
            assertEquals(1L, releasePong.count)
            transport.enqueue(listOf(down.copy(action = Protocol.ACTION_UP, buttons = 0, pressure = 0f),
                down.copy(action = Protocol.ACTION_CANCEL, buttons = 0, pressure = 0f)))
            until { link.eventFrames().size == 2 }
            assertEquals(1L, releasePong.count)
            assertEquals(PenTransport.State.CONNECTED, transport.snapshot.state)
        } finally { releasePong.countDown(); transport.stop() }
    }

    @Test fun missingPongTimesOutEvenWhenEventWritesKeepProgressing() {
        val link = object : Link(Raw()) {
            override fun receive(timeoutMillis: Int): Protocol.Packet {
                raw.closedSignal.await(5, TimeUnit.SECONDS)
                throw IOException("closed pending heartbeat")
            }
        }
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(link.raw); link },
            retryMillis = 5000, stallMillis = 10000)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.CONNECTED }
            transport.resumeCapture(transport.snapshot.generation)
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4)
            while (transport.snapshot.state == PenTransport.State.CONNECTED && System.nanoTime() < deadline) {
                transport.enqueue(listOf(down.copy(action = Protocol.ACTION_MOVE)))
                Thread.sleep(5)
            }
            until { transport.snapshot.state == PenTransport.State.COOLDOWN }
            assertTrue(link.eventFrames().isNotEmpty())
            assertTrue(link.raw.isClosed)
        } finally { transport.stop() }
    }

    @Test fun stopCancelsPendingControlReadAndJoinsItsWorker() {
        val receiving = CountDownLatch(1)
        val exited = CountDownLatch(1)
        val link = object : Link(Raw()) {
            override fun receive(timeoutMillis: Int): Protocol.Packet {
                receiving.countDown()
                try { raw.closedSignal.await(2, TimeUnit.SECONDS); throw IOException("closed") }
                finally { exited.countDown() }
            }
        }
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(link.raw); link })
        transport.start()
        assertTrue(receiving.await(1, TimeUnit.SECONDS))
        transport.stop()
        assertEquals(0L, exited.count)
        assertTrue(link.raw.isClosed)
        assertEquals(PenTransport.State.DISCONNECTED, transport.snapshot.state)
    }

    @Test fun mismatchedAsynchronousPongInvalidatesTheSession() {
        val link = object : Link(Raw()) {
            override fun receive(timeoutMillis: Int) = Protocol.Packet(Protocol.PKT_PONG, (ping + 1).toShort(), byteArrayOf())
        }
        val transport = PenTransport(endpoint, {}, { _, publish -> publish(link.raw); link }, retryMillis = 5000)
        try {
            transport.start()
            until { transport.snapshot.state == PenTransport.State.COOLDOWN }
            assertTrue(link.raw.isClosed)
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
