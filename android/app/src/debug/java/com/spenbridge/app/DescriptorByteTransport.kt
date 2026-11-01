package com.spenbridge.app

import android.os.ParcelFileDescriptor
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import java.io.IOException
import java.net.SocketException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Nonblocking IPC socket, never a raw accessory FD. One reader, one writer. */
@androidx.annotation.RequiresApi(30)
internal class DescriptorByteTransport(
    private val owner: ParcelFileDescriptor,
    private val onClose: () -> Unit = {}
) : DuplexByteTransport {
    private val descriptor = owner.fileDescriptor
    private val closed = AtomicBoolean(false)
    private val readPoll = arrayOf(StructPollfd().apply {
        fd = descriptor; events = OsConstants.POLLIN.toShort()
    })
    private val writePoll = arrayOf(StructPollfd().apply {
        fd = descriptor; events = OsConstants.POLLOUT.toShort()
    })

    init {
        try {
            val flags = Os.fcntlInt(descriptor, OsConstants.F_GETFL, 0)
            Os.fcntlInt(descriptor, OsConstants.F_SETFL, flags or OsConstants.O_NONBLOCK)
        } catch (error: ErrnoException) {
            owner.close()
            throw IOException("Cannot configure diagnostic IPC socket", error)
        }
    }

    private fun checkOpen() {
        if (closed.get()) throw SocketException("Diagnostic IPC socket is closed")
    }
    private fun range(bytes: ByteArray, offset: Int, size: Int) {
        if (offset < 0 || size < 0 || offset > bytes.size - size) throw IndexOutOfBoundsException()
    }
    private fun deadline(timeoutMillis: Int): Long =
        if (timeoutMillis == 0) Long.MAX_VALUE
        else System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())

    private fun awaitReady(poll: Array<StructPollfd>, until: Long) {
        while (true) {
            checkOpen()
            val remaining = until - System.nanoTime()
            if (remaining <= 0) throw SocketTimeoutException("Diagnostic IPC deadline expired")
            // This is a cancellation polling bound, not an input batching wait.
            val wait = TimeUnit.NANOSECONDS.toMillis(remaining).coerceIn(1, 25).toInt()
            try {
                poll[0].revents = 0
                if (Os.poll(poll, wait) > 0) {
                    checkOpen()
                    if (poll[0].revents.toInt() and OsConstants.POLLNVAL != 0) throw SocketException("Invalid diagnostic IPC socket")
                    return
                }
            } catch (error: ErrnoException) {
                if (error.errno != OsConstants.EINTR) throw IOException("Diagnostic IPC poll failed", error)
            }
        }
    }
    private fun retry(error: ErrnoException): Boolean =
        error.errno == OsConstants.EAGAIN || error.errno == OsConstants.EINTR

    override fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int): Int {
        require(timeoutMillis >= 0)
        range(bytes, offset, size)
        checkOpen()
        if (size == 0) return 0
        val until = deadline(timeoutMillis)
        while (true) {
            awaitReady(readPoll, until)
            try {
                val count = Os.read(descriptor, bytes, offset, size)
                return if (count == 0) -1 else count
            } catch (error: ErrnoException) {
                if (!retry(error)) throw IOException("Diagnostic IPC read failed", error)
            }
        }
    }
    override fun write(bytes: ByteArray, offset: Int, size: Int) {
        range(bytes, offset, size)
        checkOpen()
        var written = 0
        var until = deadline(2000)
        while (written < size) {
            awaitReady(writePoll, until)
            try {
                val count = Os.write(descriptor, bytes, offset + written, size - written)
                if (count <= 0) throw IOException("Diagnostic IPC write made no progress")
                written += count
                until = deadline(2000)
            } catch (error: ErrnoException) {
                if (!retry(error)) throw IOException("Diagnostic IPC write failed", error)
            }
        }
    }
    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        try { Os.shutdown(descriptor, OsConstants.SHUT_RDWR) } catch (_: ErrnoException) { }
        try { owner.close() } finally { onClose() }
    }
}
