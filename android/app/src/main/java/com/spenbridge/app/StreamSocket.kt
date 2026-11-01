package com.spenbridge.app

import java.io.Closeable
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketAddress
import java.net.SocketException
import java.util.concurrent.atomic.AtomicBoolean

/** A connected byte transport for TLS without TCP/ADB.
 * Implementations MUST honor read deadlines and close MUST cancel pending I/O.
 * A raw blocking accessory descriptor alone does not satisfy this contract.
 */
interface DuplexByteTransport : Closeable {
    fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int): Int
    fun write(bytes: ByteArray, offset: Int, size: Int)
}

/** Public SSLSocketFactory stream adapter. No hidden APIs or plaintext fallback.
 * One reader and one writer may operate concurrently, as with an ordinary socket.
 */
class StreamSocket(private val transport: DuplexByteTransport) : Socket() {
    private val closed = AtomicBoolean(false)
    @Volatile private var readTimeout = 0
    private val address = InetAddress.getLoopbackAddress()
    private val input = object : InputStream() {
        private val one = ByteArray(1)
        @Synchronized override fun read(): Int {
            val count = read(one, 0, 1)
            return if (count < 0) -1 else one[0].toInt() and 255
        }
        override fun read(bytes: ByteArray, offset: Int, length: Int): Int {
            requireRange(bytes, offset, length)
            checkOpen()
            if (length == 0) return 0
            val count = transport.read(bytes, offset, length, readTimeout)
            if (count == 0 || count < -1 || count > length) throw IOException("Invalid byte transport read")
            return count
        }
        override fun close() { this@StreamSocket.close() }
    }
    private val output = object : OutputStream() {
        private val one = ByteArray(1)
        @Synchronized override fun write(value: Int) {
            one[0] = value.toByte(); write(one, 0, 1)
        }
        override fun write(bytes: ByteArray, offset: Int, length: Int) {
            requireRange(bytes, offset, length)
            checkOpen()
            if (length != 0) transport.write(bytes, offset, length)
        }
        override fun close() { this@StreamSocket.close() }
    }
    private fun requireRange(bytes: ByteArray, offset: Int, length: Int) {
        if (offset < 0 || length < 0 || offset > bytes.size - length) throw IndexOutOfBoundsException()
    }
    private fun checkOpen() { if (closed.get()) throw SocketException("Byte transport is closed") }
    override fun getInputStream(): InputStream { checkOpen(); return input }
    override fun getOutputStream(): OutputStream { checkOpen(); return output }
    override fun isConnected(): Boolean = true
    override fun isBound(): Boolean = true
    override fun isClosed(): Boolean = closed.get()
    override fun isInputShutdown(): Boolean = closed.get()
    override fun isOutputShutdown(): Boolean = closed.get()
    override fun getInetAddress(): InetAddress = address
    override fun getLocalAddress(): InetAddress = address
    override fun getPort(): Int = 0
    override fun getLocalPort(): Int = 0
    override fun getRemoteSocketAddress(): SocketAddress = InetSocketAddress(address, 0)
    override fun getLocalSocketAddress(): SocketAddress = InetSocketAddress(address, 0)
    override fun setSoTimeout(timeout: Int) {
        require(timeout >= 0); checkOpen(); readTimeout = timeout
    }
    override fun getSoTimeout(): Int = readTimeout
    override fun setTcpNoDelay(on: Boolean) { checkOpen() }
    override fun getTcpNoDelay(): Boolean = true
    override fun shutdownInput() { close() }
    override fun shutdownOutput() { close() }
    override fun close() { if (closed.compareAndSet(false, true)) transport.close() }
}
