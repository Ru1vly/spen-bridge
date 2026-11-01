package com.spenbridge.app

import android.content.Context
import android.os.ParcelFileDescriptor
import android.os.Process
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.locks.LockSupport

/** Emulator-only lifecycle/byte tests. Not a physical USB or latency benchmark. */
@androidx.annotation.RequiresApi(30)
internal object AccessoryTransportSelfTest {
    private fun exact(socket: Socket, count: Int): ByteArray {
        val result = ByteArray(count)
        var offset = 0
        while (offset < count) {
            val n = socket.inputStream.read(result, offset, count-offset)
            check(n > 0) { "Unexpected stream EOF" }
            offset += n
        }
        return result
    }
    private fun checkRun(results: JSONArray, name: String, block: () -> Unit) {
        val start = System.nanoTime()
        try { block() } catch (error: Throwable) { throw AssertionError(name, error) }
        results.put(JSONObject().put("name", name).put("passed", true)
            .put("duration_ms", (System.nanoTime()-start)/1_000_000.0))
    }
    private fun senderCapacity(context: Context, endpoint: ConnectionEndpoint, rate: Int, base: Int, trace: Boolean): JSONObject {
        val count = rate * 2
        val ready = CountDownLatch(1)
        val failed = AtomicReference<Throwable?>()
        val writes = LongArray(count)
        val states = java.util.Collections.synchronizedList(mutableListOf<String>())
        var written = 0
        lateinit var transport: PenTransport
        transport = PenTransport(endpoint, { update ->
            states.add(update.state.name)
            if (update.state == PenTransport.State.CONNECTED) {
                transport.resumeCapture(update.generation)
                ready.countDown()
            }
        }, openLink = { target, publish ->
            val tcp = Socket()
            var session: AccessoryStreamConnection? = null
            try {
                check(publish(tcp)) { "Sender connection cancelled" }
                tcp.tcpNoDelay = true
                tcp.connect(java.net.InetSocketAddress(target.host, target.port), 3000)
                val active = AccessoryStreamConnection.openFixture(context, ParcelFileDescriptor.fromSocket(tcp), publish=publish)
                session = active
                val link = SocketProtocolLink.openStream(target, active.socket, publish=publish)
                object : ProtocolLink {
                    override fun send(packet: ByteArray) { send(packet, packet.size) }
                    override fun send(packet: ByteArray, size: Int) {
                        val before = System.nanoTime()
                        link.send(packet, size)
                        if (size >= Protocol.HEADER_SIZE && packet[4] == Protocol.PKT_EVENT) {
                            if (written < writes.size) writes[written] = System.nanoTime()-before
                            written++
                        }
                    }
                    override fun receive(timeoutMillis: Int): Protocol.Packet = link.receive(timeoutMillis)
                    override fun close() {
                        try { link.close() } finally { active.close(); tcp.close() }
                    }
                }
            } catch (error: Throwable) {
                try { session?.close() } finally { tcp.close() }
                failed.set(error)
                throw error
            }
        })
        var first = 0L
        var last = 0L
        var longestSourceGap = 0L
        if (trace) InputTrace.start(context, 15)
        try {
            transport.start()
            check(ready.await(6, TimeUnit.SECONDS)) { "Production sender did not connect" }
            val start = System.nanoTime()
            for (index in 0 until count) {
                val deadline = start + index*1_000_000_000L/rate
                while (true) {
                    val remaining = deadline-System.nanoTime()
                    if (remaining <= 0) break
                    LockSupport.parkNanos(remaining)
                }
                val now = System.nanoTime()
                if (index == 0) first = now
                else longestSourceGap = maxOf(longestSourceGap, now-last)
                last = now
                if (trace) InputTrace.synthetic(now, base+index)
                transport.enqueue(listOf(Protocol.Event(Protocol.ACTION_HOVER_MOVE, 0, 0,
                    (base+index)/20000f, .5f, 0f)))
            }
            Thread.sleep(300)
        } finally {
            try { transport.stop() } finally { if (trace) InputTrace.stop() }
        }
        var traceFile: String? = null
        if (trace) {
            val until = System.nanoTime()+TimeUnit.SECONDS.toNanos(3)
            while (InputTrace.status().startsWith("exporting:") && System.nanoTime() < until) Thread.sleep(10)
            val status = InputTrace.status()
            check(status.startsWith("ready:")) { "Sender trace export failed" }
            traceFile = status.substringAfter(":")
        }
        val measured = writes.take(minOf(written, count)).sorted()
        return JSONObject().put("trace_enabled", trace).put("trace_file", traceFile ?: JSONObject.NULL)
            .put("rate_target", rate).put("offered", count).put("packets_written", written)
            .put("all_packets_written", failed.get() == null && written == count)
            .put("connection_error", failed.get()?.javaClass?.simpleName ?: JSONObject.NULL)
            .put("transport_states", JSONArray(states.toList()))
            .put("actual_source_packets_per_second", (count-1)*1e9/(last-first))
            .put("longest_source_gap_us", longestSourceGap/1000.0)
            .put("tls_write_p50_us", measured.getOrNull(measured.size/2)?.div(1000.0) ?: JSONObject.NULL)
            .put("tls_write_p99_us", measured.getOrNull((measured.size*99)/100)?.div(1000.0) ?: JSONObject.NULL)
            .put("tls_write_max_us", measured.lastOrNull()?.div(1000.0) ?: JSONObject.NULL)
    }
    fun run(context: Context, tlsConfig: JSONObject?): JSONObject {
        val results = JSONArray()
        val appPid = Process.myPid()
        checkRun(results, "descriptor_read_timeout") {
            val pair = ParcelFileDescriptor.createSocketPair()
            StreamSocket(DescriptorByteTransport(pair[0])).use { socket ->
                try {
                    socket.soTimeout = 25
                    try { socket.inputStream.read(); error("Missing read timeout") }
                    catch (_: SocketTimeoutException) { }
                } finally { pair[1].close() }
            }
        }
        checkRun(results, "descriptor_close_cancels_blocked_write") {
            val pair = ParcelFileDescriptor.createSocketPair()
            StreamSocket(DescriptorByteTransport(pair[0])).use { socket ->
                val outcome = AtomicReference<Throwable?>()
                val entered = CountDownLatch(1)
                val writer = Thread {
                    entered.countDown()
                    try { socket.outputStream.write(ByteArray(4*1024*1024)); error("Unexpected write completion") }
                    catch (error: Throwable) { outcome.set(error) }
                }
                try {
                    writer.start()
                    check(entered.await(1, TimeUnit.SECONDS))
                    Thread.sleep(50)
                    check(writer.isAlive) { "Write did not block" }
                    socket.close()
                    writer.join(1000)
                    check(!writer.isAlive && outcome.get() is IOException) { "Blocked writer survived close" }
                } finally { socket.close(); pair[1].close(); writer.join(1000) }
            }
        }
        checkRun(results, "helper_close_cancels_blocked_read") {
            val fixture = ParcelFileDescriptor.createSocketPair()
            try {
                AccessoryStreamConnection.openFixture(context, fixture[0]).use { session ->
                    check(session.helperPid != appPid)
                    session.socket.soTimeout = 0
                    val failed = AtomicReference<Throwable?>()
                    val reader = Thread {
                        try { check(session.socket.inputStream.read() == -1) }
                        catch (_: IOException) { }
                        catch (error: Throwable) { failed.set(error) }
                    }
                    reader.start()
                    Thread.sleep(50)
                    check(reader.isAlive) { "Read did not block" }
                    session.close()
                    reader.join(1000)
                    check(!reader.isAlive && failed.get() == null) { "Blocked reader cancellation failed" }
                    check(session.awaitHelperStopped(2000)) { "Helper survived explicit cancellation" }
                }
            } finally { fixture.forEach { it.close() } }
        }
        checkRun(results, "helper_stop_independent_of_parent_main_looper") {
            val fixture = ParcelFileDescriptor.createSocketPair()
            try {
                AccessoryStreamConnection.openFixture(context, fixture[0]).use { session ->
                    val entered = CountDownLatch(1)
                    val release = CountDownLatch(1)
                    android.os.Handler(android.os.Looper.getMainLooper()).post {
                        entered.countDown()
                        release.await(1500, TimeUnit.MILLISECONDS)
                    }
                    try {
                        check(entered.await(1, TimeUnit.SECONDS))
                        session.close()
                        check(session.awaitHelperStopped(500)) { "Helper stop depends on blocked parent main looper" }
                    } finally {
                        release.countDown()
                        session.close()
                        check(session.awaitHelperStopped(2000))
                    }
                }
            } finally { fixture.forEach { it.close() } }
        }
        checkRun(results, "helper_preserves_multibuffer_bytes") {
            val fixture = ParcelFileDescriptor.createSocketPair()
            try {
                StreamSocket(DescriptorByteTransport(fixture[1])).use { host ->
                    AccessoryStreamConnection.openFixture(context, fixture[0]).use { session ->
                        host.soTimeout = 3000
                        session.socket.soTimeout = 3000
                        val a = ByteArray(16_384*5+211) { (it*19).toByte() }
                        val b = ByteArray(a.size) { (it*31+7).toByte() }
                        val failed = AtomicReference<Throwable?>()
                        val writers = listOf(
                            Thread { try { host.outputStream.write(a) } catch (t: Throwable) { failed.set(t) } },
                            Thread { try { session.socket.outputStream.write(b) } catch (t: Throwable) { failed.set(t) } })
                        try {
                            writers.forEach { it.start() }
                            check(exact(session.socket, a.size).contentEquals(a)) { "USB-to-app bytes changed" }
                            check(exact(host, b.size).contentEquals(b)) { "App-to-USB bytes changed" }
                            writers.forEach { it.join(1000); check(!it.isAlive) }
                            check(failed.get() == null) { "Writer failed" }
                        } finally {
                            session.close(); host.close(); writers.forEach { it.join(1000) }
                        }
                        check(session.awaitHelperStopped(2000))
                    }
                }
            } finally { fixture.forEach { it.close() } }
        }
        checkRun(results, "helper_watchdog_terminates_idle_io") {
            val fixture = ParcelFileDescriptor.createSocketPair()
            try {
                AccessoryStreamConnection.openFixture(context, fixture[0], lifetimeSeconds=1).use { session ->
                    session.socket.soTimeout = 3000
                    try { check(session.socket.inputStream.read() == -1) } catch (_: IOException) { }
                    check(session.awaitHelperStopped(2000)) { "Helper watchdog did not terminate process" }
                }
            } finally { fixture.forEach { it.close() } }
        }
        checkRun(results, "cancel_before_bind") {
            val fixture = ParcelFileDescriptor.createSocketPair()
            try {
                try {
                    AccessoryStreamConnection.openFixture(context, fixture[0], publish={ it.close(); false })
                    error("Cancelled open succeeded")
                } catch (_: InterruptedException) { }
            } finally { fixture.forEach { it.close() } }
        }
        if (tlsConfig != null) {
            for (wrongPin in listOf(true, false)) {
                checkRun(results, if (wrongPin) "android_rejects_wrong_pin_over_helper" else "android_rejects_wrong_pairing_over_helper") {
                    val goodCode = tlsConfig.getString("code")
                    val badCode = (if (goodCode[0] == 'A') "B" else "A") + goodCode.substring(1)
                    val endpoint = ConnectionEndpoint("127.0.0.1", tlsConfig.getInt("port"),
                        if (wrongPin) "00".repeat(32) else tlsConfig.getString("fingerprint"),
                        if (wrongPin) goodCode else badCode)
                    Socket().use { tcp ->
                        tcp.tcpNoDelay = true
                        tcp.connect(java.net.InetSocketAddress(endpoint.host, endpoint.port), 3000)
                        AccessoryStreamConnection.openFixture(context, ParcelFileDescriptor.fromSocket(tcp)).use { session ->
                            try {
                                SocketProtocolLink.openStream(endpoint, session.socket, publish={ true }).close()
                                error("Untrusted accessory connection accepted")
                            } catch (_: IOException) { }
                            session.close()
                            check(session.awaitHelperStopped(2000))
                        }
                    }
                }
            }
        }
        if (tlsConfig != null) checkRun(results, "android_conscrypt_pinned_tls_over_helper") {
            val endpoint = ConnectionEndpoint("127.0.0.1", tlsConfig.getInt("port"),
                tlsConfig.getString("fingerprint"), tlsConfig.getString("code"))
            // A loopback TCP descriptor stands in for accessory USB. Encryption
            // starts in the parent process and passes opaquely through helper.
            Socket().use { tcp ->
                tcp.tcpNoDelay = true
                tcp.connect(java.net.InetSocketAddress(endpoint.host, endpoint.port), 3000)
                AccessoryStreamConnection.openFixture(context, ParcelFileDescriptor.fromSocket(tcp)).use { session ->
                    SocketProtocolLink.openStream(endpoint, session.socket, publish={ true }).use { link ->
                        link.send(Protocol.packEvents(listOf(Protocol.Event(Protocol.ACTION_HOVER_MOVE, 0, 0, .5f, .5f, 0f))))
                        link.send(Protocol.packPing(321))
                        val pong = link.receive(2000)
                        check(pong.kind == Protocol.PKT_PONG && pong.sequence.toInt() == 321)
                    }
                    check(session.awaitHelperStopped(2000))
                }
            }
        }
        val capacity = JSONArray()
        if (tlsConfig != null) {
            val endpoint = ConnectionEndpoint("127.0.0.1", tlsConfig.getInt("port"),
                tlsConfig.getString("fingerprint"), tlsConfig.getString("code"))
            for ((rate, base) in listOf(1000 to 0, 3000 to 2000)) {
                capacity.put(senderCapacity(context, endpoint, rate, base, tlsConfig.optBoolean("trace", false)))
            }
        }
        return JSONObject().put("scope", "Android emulator; simulated USB; no physical input")
            .put("main_pid", appPid).put("main_process_preserved", Process.myPid() == appPid)
            .put("checks", results).put("pinned_tls_tested", tlsConfig != null).put("synthetic_capacity", capacity)
    }
}
