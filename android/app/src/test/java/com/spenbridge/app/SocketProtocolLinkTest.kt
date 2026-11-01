package com.spenbridge.app

import java.io.DataInputStream
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLServerSocket
import org.junit.Assert.*
import org.junit.Test

/** Real loopback TLS, using an explicitly test-only certificate/key fixture. */
class SocketProtocolLinkTest {
    private val code = "a".repeat(43)
    private fun fingerprint(): String {
        val cert = CertificateFactory.getInstance("X.509").generateCertificate(javaClass.getResourceAsStream("/test-server.der"))
        return MessageDigest.getInstance("SHA-256").digest(cert.encoded).joinToString("") { "%02x".format(it.toInt() and 255) }
    }
    private fun listener(): SSLServerSocket {
        val keys = KeyStore.getInstance("PKCS12").apply { load(requireNotNull(this@SocketProtocolLinkTest.javaClass.getResourceAsStream("/test-server.p12")), "test-only".toCharArray()) }
        val managers = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm()).apply { init(keys, "test-only".toCharArray()) }
        val context = SSLContext.getInstance("TLS").apply { init(managers.keyManagers, null, null) }
        return (context.serverSocketFactory.createServerSocket(0, 1, InetAddress.getLoopbackAddress()) as SSLServerSocket).apply { soTimeout = 3000 }
    }
    private fun read(input: DataInputStream): Protocol.Packet {
        val bytes = ByteArray(9).also { input.readFully(it) }
        val header = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        val magic = ByteArray(4).also { header.get(it) }
        check(magic.contentEquals(Protocol.MAGIC))
        val kind = header.get()
        val sequence = header.short
        val size = header.short.toInt() and 65535
        return Protocol.Packet(kind, sequence, ByteArray(size).also { input.readFully(it) })
    }

    @Test fun pinnedTlsCompletesMutualProofAndSequencedHeartbeat() {
        listener().use { server ->
            val executor = Executors.newSingleThreadExecutor()
            val task = executor.submit {
                server.accept().use { socket ->
                    socket.soTimeout = 3000
                    val input = DataInputStream(socket.getInputStream())
                    val output = socket.getOutputStream()
                    val nonce = ByteArray(32) { it.toByte() }
                    output.write(Protocol.packHandshake(proof = PairingProtocol.VERSION + nonce))
                    val client = read(input)
                    check(PairingProtocol.verifyProof(code, nonce, "client", client.payload))
                    output.write(Protocol.packHandshake(proof = PairingProtocol.proof(code, nonce, "server")))
                    val ping = read(input)
                    check(ping.kind == Protocol.PKT_PING && ping.payload.isEmpty())
                    socket.soTimeout = 100
                    assertThrows(java.net.SocketTimeoutException::class.java) { input.readByte() }
                    output.write(Protocol.packPacket(Protocol.PKT_PONG, ping.sequence, byteArrayOf()))
                }
            }
            try {
                SocketProtocolLink.open(ConnectionEndpoint("127.0.0.1", server.localPort, fingerprint(), code)) { true }.use { link ->
                    val storage = ByteArray(128) { 0x7f }
                    val ping = Protocol.packPing(42)
                    ping.copyInto(storage)
                    link.send(storage, ping.size)
                    val reply = link.receive(1000)
                    assertEquals(Protocol.PKT_PONG, reply.kind)
                    assertEquals(42, reply.sequence.toInt())
                }
                task.get(4, TimeUnit.SECONDS)
            } catch (failure: Throwable) {
                try { task.get(4, TimeUnit.SECONDS) } catch (serverFailure: Exception) { failure.addSuppressed(serverFailure) }
                throw failure
            } finally { executor.shutdownNow() }
        }
    }

    @Test fun pinnedTlsWorksOverCancellableStreamsWithoutATcpSocketDescriptor() {
        listener().use { server ->
            val executor = Executors.newSingleThreadExecutor()
            val task = executor.submit {
                server.accept().use { socket ->
                    socket.soTimeout = 3000
                    val input = DataInputStream(socket.getInputStream())
                    val output = socket.getOutputStream()
                    val nonce = ByteArray(32) { (it + 3).toByte() }
                    output.write(Protocol.packHandshake(proof = PairingProtocol.VERSION + nonce))
                    val request = read(input)
                    check(PairingProtocol.verifyProof(code, nonce, "client", request.payload))
                    output.write(Protocol.packHandshake(proof = PairingProtocol.proof(code, nonce, "server")))
                    val ping = read(input)
                    check(ping.kind == Protocol.PKT_PING && ping.payload.isEmpty())
                    output.write(Protocol.packPacket(Protocol.PKT_PONG, ping.sequence))
                }
            }
            val tcp = java.net.Socket("127.0.0.1", server.localPort)
            val transport = object : DuplexByteTransport {
                override fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int): Int {
                    tcp.soTimeout = timeoutMillis
                    return tcp.getInputStream().read(bytes, offset, size)
                }
                override fun write(bytes: ByteArray, offset: Int, size: Int) { tcp.getOutputStream().write(bytes, offset, size) }
                override fun close() { tcp.close() }
            }
            val stream = StreamSocket(transport)
            try {
                SocketProtocolLink.openStream(ConnectionEndpoint("127.0.0.1", server.localPort, fingerprint(), code), stream, publish = { true }).use { link ->
                    link.send(Protocol.packPing(77))
                    val pong = link.receive(1000)
                    assertEquals(Protocol.PKT_PONG, pong.kind)
                    assertEquals(77, pong.sequence.toInt())
                }
                assertTrue(stream.isClosed)
                assertTrue(tcp.isClosed)
                task.get(4, TimeUnit.SECONDS)
            } catch (failure: Throwable) {
                try { task.get(4, TimeUnit.SECONDS) } catch (peer: Exception) { failure.addSuppressed(peer) }
                throw failure
            } finally { stream.close(); executor.shutdownNow() }
        }
    }

    @Test fun readinessProbeAuthenticatesWithoutSendingInputOrClaimingAStream() {
        listener().use { server ->
            val executor = Executors.newSingleThreadExecutor()
            val task = executor.submit {
                server.accept().use { socket ->
                    socket.soTimeout = 3000
                    val input = DataInputStream(socket.getInputStream())
                    val output = socket.getOutputStream()
                    val nonce = ByteArray(32) { (it + 1).toByte() }
                    output.write(Protocol.packHandshake(proof = PairingProtocol.VERSION + nonce))
                    val request = read(input)
                    check(request.kind == Protocol.PKT_HANDSHAKE && request.sequence.toInt() == 1)
                    check(PairingProtocol.verifyProof(code, nonce, "client", request.payload))
                    output.write(Protocol.packHandshake(seq = 1, proof = PairingProtocol.proof(code, nonce, "server")))
                    check(input.read() == -1)
                }
            }
            try {
                assertTrue(SocketProtocolLink.probe(ConnectionEndpoint("127.0.0.1", server.localPort, fingerprint(), code)) { true })
                task.get(4, TimeUnit.SECONDS)
            } finally { executor.shutdownNow() }
        }
    }

    @Test fun wrongPinFailsBeforeAnyPairingCodeProofIsSent() {
        listener().use { server ->
            val executor = Executors.newSingleThreadExecutor()
            val task = executor.submit {
                server.accept().use { socket ->
                    socket.soTimeout = 3000
                    try {
                        assertEquals(-1, socket.getInputStream().read())
                    } catch (_: javax.net.ssl.SSLException) { }
                    catch (_: java.net.SocketException) { /* Peer may reset during TLS rejection. */ }
                }
            }
            try {
                try {
                    SocketProtocolLink.open(ConnectionEndpoint("127.0.0.1", server.localPort, "00".repeat(32), code)) { true }.close()
                    fail("Wrong pin accepted")
                } catch (_: javax.net.ssl.SSLException) { }
                task.get(4, TimeUnit.SECONDS)
            } finally { executor.shutdownNow() }
        }
    }
}
