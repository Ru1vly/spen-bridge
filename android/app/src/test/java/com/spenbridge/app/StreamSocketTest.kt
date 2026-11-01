package com.spenbridge.app

import java.io.EOFException
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Test

class StreamSocketTest {
    @Test fun timeoutsAndRangesAreDelegatedWithoutLeakingUnusedBytes() {
        var timeout = -1
        var written = byteArrayOf()
        val transport = object : DuplexByteTransport {
            override fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int): Int {
                timeout = timeoutMillis; bytes[offset] = 42; return 1
            }
            override fun write(bytes: ByteArray, offset: Int, size: Int) { written = bytes.copyOfRange(offset, offset + size) }
            override fun close() {}
        }
        StreamSocket(transport).use { socket ->
            socket.soTimeout = 123
            assertEquals(42, socket.getInputStream().read())
            assertEquals(123, timeout)
            socket.getOutputStream().write(byteArrayOf(1, 2, 3, 4), 1, 2)
            assertArrayEquals(byteArrayOf(2, 3), written)
            assertThrows(IndexOutOfBoundsException::class.java) { socket.getOutputStream().write(byteArrayOf(1), 1, 1) }
        }
    }

    @Test fun closingTheAdapterCancelsABlockedReadExactlyOnce() {
        val entered = CountDownLatch(1); val closed = CountDownLatch(1)
        var closes = 0
        val transport = object : DuplexByteTransport {
            override fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int): Int {
                entered.countDown(); check(closed.await(2, TimeUnit.SECONDS)); throw EOFException("closed")
            }
            override fun write(bytes: ByteArray, offset: Int, size: Int) {}
            override fun close() { closes++; closed.countDown() }
        }
        val socket = StreamSocket(transport); val executor = Executors.newSingleThreadExecutor()
        try {
            val task = executor.submit<Boolean> {
                try { socket.getInputStream().read(); false } catch (_: IOException) { true }
            }
            assertTrue(entered.await(1, TimeUnit.SECONDS))
            socket.close(); socket.close()
            assertTrue(task.get(1, TimeUnit.SECONDS)); assertEquals(1, closes)
        } finally { socket.close(); executor.shutdownNow() }
    }

    @Test fun invalidZeroProgressReadFailsInsteadOfBusySpinning() {
        val transport = object : DuplexByteTransport {
            override fun read(bytes: ByteArray, offset: Int, size: Int, timeoutMillis: Int) = 0
            override fun write(bytes: ByteArray, offset: Int, size: Int) {}
            override fun close() {}
        }
        StreamSocket(transport).use { socket ->
            assertThrows(IOException::class.java) { socket.getInputStream().read() }
        }
    }
}
