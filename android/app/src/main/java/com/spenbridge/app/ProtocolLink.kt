package com.spenbridge.app

import java.io.EOFException
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.FutureTask
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLSocket

interface ProtocolLink : AutoCloseable {
    fun send(packet: ByteArray)
    fun receive(timeoutMillis: Int): Protocol.Packet
}

/** One bounded DNS worker; callers can cancel their wait even during OS DNS. */
private object EndpointResolver {
    private val executor = ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS, ArrayBlockingQueue<Runnable>(1),
        { work -> Thread(work, "SPenDNS").apply { isDaemon = true } }, ThreadPoolExecutor.AbortPolicy()).apply {
        allowCoreThreadTimeOut(true)
    }
    fun resolve(host: String, timeout: Long): InetAddress {
        executor.purge()
        val task = FutureTask { InetAddress.getAllByName(host).first() }
        executor.execute(task)
        return try { task.get(timeout, TimeUnit.MILLISECONDS) } finally { task.cancel(true) }
    }
}

class SocketProtocolLink private constructor(private val socket: SSLSocket) : ProtocolLink {
    override fun send(packet: ByteArray) { socket.outputStream.write(packet) }
    override fun close() { socket.close() }

    override fun receive(timeoutMillis: Int): Protocol.Packet {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())
        val input = socket.inputStream
        fun exact(size: Int): ByteArray {
            val bytes = ByteArray(size)
            var offset = 0
            while (offset < size) {
                val remaining = TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime())
                if (remaining <= 0) throw SocketTimeoutException("Desktop frame deadline expired")
                socket.soTimeout = remaining.coerceAtMost(Int.MAX_VALUE.toLong()).toInt().coerceAtLeast(1)
                val count = input.read(bytes, offset, size - offset)
                if (count < 0) throw EOFException("Desktop closed the session")
                offset += count
            }
            return bytes
        }
        val header = ByteBuffer.wrap(exact(Protocol.HEADER_SIZE)).order(ByteOrder.LITTLE_ENDIAN)
        val magic = ByteArray(4).also { header.get(it) }
        if (!magic.contentEquals(Protocol.MAGIC)) throw IOException("Invalid desktop protocol")
        val kind = header.get()
        val sequence = header.short
        val size = header.short.toInt() and 65535
        if (!((kind == Protocol.PKT_HANDSHAKE && size == 36) || (kind == Protocol.PKT_PONG && size == 0))) {
            throw IOException("Unexpected desktop packet")
        }
        return Protocol.Packet(kind, sequence, exact(size))
    }

    companion object {
        fun open(endpoint: ConnectionEndpoint, publish: (Socket) -> Boolean): ProtocolLink {
            require(ConnectionEndpoint.validHost(endpoint.host) && endpoint.port in 1..65535 && endpoint.isPaired())
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
            fun remaining(): Int = TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime()).toInt().also {
                if (it <= 0) throw SocketTimeoutException("Desktop connection deadline expired")
            }
            val raw = Socket()
            var tls: SSLSocket? = null
            try {
                // Published before DNS/connect; cancellation always owns a closable
                // raw socket, including while TLS holds a write lock.
                if (!publish(raw)) throw InterruptedException("Connection attempt was cancelled")
                val address = EndpointResolver.resolve(endpoint.host, remaining().coerceAtMost(3000).toLong())
                raw.tcpNoDelay = true
                raw.connect(InetSocketAddress(address, endpoint.port), remaining())
                tls = PairingProtocol.socketFactory(endpoint.fingerprint)
                    .createSocket(raw, endpoint.host, endpoint.port, true) as SSLSocket
                tls.enabledProtocols = tls.supportedProtocols.filter { it in listOf("TLSv1.2", "TLSv1.3") }.toTypedArray()
                tls.soTimeout = remaining()
                tls.startHandshake()
                val link = SocketProtocolLink(tls)
                val challenge = link.receive(remaining())
                if (challenge.kind != Protocol.PKT_HANDSHAKE || challenge.sequence.toInt() != 0 ||
                    !challenge.payload.copyOfRange(0, 4).contentEquals(PairingProtocol.VERSION)) {
                    throw IOException("Desktop pairing version mismatch")
                }
                val nonce = challenge.payload.copyOfRange(4, 36)
                link.send(Protocol.packHandshake(proof = PairingProtocol.proof(endpoint.code, nonce, "client")))
                val reply = link.receive(remaining())
                if (reply.kind != Protocol.PKT_HANDSHAKE || reply.sequence.toInt() != 0 ||
                    !PairingProtocol.verifyProof(endpoint.code, nonce, "server", reply.payload)) {
                    throw IOException("Desktop pairing proof mismatch")
                }
                return link
            } catch (failure: Throwable) {
                try { raw.close() } catch (_: IOException) { }
                try { tls?.close() } catch (_: IOException) { }
                throw failure
            }
        }
    }
}
