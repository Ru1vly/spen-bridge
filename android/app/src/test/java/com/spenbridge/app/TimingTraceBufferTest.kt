package com.spenbridge.app

import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import org.junit.Assert.*
import org.junit.Test

class TimingTraceBufferTest {
    @Test fun boundedCaptureReportsOverflowAndCannotAppendAfterFreeze() {
        val buffer = TimingTraceBuffer(2)
        repeat(3) { buffer.append(3, 1, it.toLong(), 1, 10, 20, 30, 40) }
        buffer.freeze()
        buffer.append(3, 1, 99, 1, 10, 20, 30, 40)
        assertEquals(3L, buffer.seen)
        assertEquals(2, buffer.stored)
        val bytes = ByteArrayOutputStream()
        buffer.writeTo(DataOutputStream(bytes))
        assertEquals(128, bytes.size())
        val input = DataInputStream(bytes.toByteArray().inputStream())
        repeat(2) { sequence ->
            assertEquals(3L, input.readLong()); assertEquals(1L, input.readLong())
            assertEquals(sequence.toLong(), input.readLong()); assertEquals(1L, input.readLong())
            assertEquals(10L, input.readLong()); assertEquals(20L, input.readLong())
            assertEquals(30L, input.readLong()); assertEquals(40L, input.readLong())
        }
    }

    @Test fun concurrentWritersCannotTearRecords() {
        val buffer = TimingTraceBuffer(4000)
        val threads = List(4) { thread -> Thread {
            repeat(1000) { buffer.append(1, thread.toLong(), it.toLong(), 1, 10, 20, 30, 40) }
        }.apply { start() } }
        threads.forEach { it.join() }
        buffer.freeze()
        assertEquals(4000L, buffer.seen)
        assertEquals(4000, buffer.stored)
        val bytes = ByteArrayOutputStream()
        buffer.writeTo(DataOutputStream(bytes))
        val input = DataInputStream(bytes.toByteArray().inputStream())
        val identities = mutableSetOf<Pair<Long,Long>>()
        repeat(4000) {
            assertEquals(1L, input.readLong())
            assertTrue(identities.add(input.readLong() to input.readLong()))
            assertEquals(1L, input.readLong()); assertEquals(10L, input.readLong())
            assertEquals(20L, input.readLong()); assertEquals(30L, input.readLong()); assertEquals(40L, input.readLong())
        }
    }

    @Test fun exportRequiresAFrozenBuffer() {
        assertThrows(IllegalStateException::class.java) {
            TimingTraceBuffer(1).writeTo(DataOutputStream(ByteArrayOutputStream()))
        }
    }
}
