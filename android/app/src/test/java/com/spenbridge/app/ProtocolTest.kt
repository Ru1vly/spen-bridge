package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ProtocolTest {
    private val event = Protocol.Event(3, 0, 5, .25f, .75f, .5f, -30f, 45f)

    @Test fun wireFormatMatchesPythonFixture() {
        val expected = "5350454e012a001800030005000000803e0000403f0000003f0000f0c100003442"
        assertEquals(expected, Protocol.packEvents(listOf(event), 42).joinToString("") { "%02x".format(it.toInt() and 255) })
    }

    @Test fun oversizedBatchIsSplitWithoutLengthWrapOrLostTransitions() {
        val events = List(2731) { index -> event.copy(action = if (index == 2730) Protocol.ACTION_UP else Protocol.ACTION_MOVE) }
        val frames = Protocol.packEventBatches(events, 32767)
        assertEquals(2, frames.size)
        for (frame in frames) {
            val header = ByteBuffer.wrap(frame).order(ByteOrder.LITTLE_ENDIAN)
            assertEquals(frame.size - Protocol.HEADER_SIZE, header.getShort(7).toInt() and 65535)
        }
        assertEquals(32768, ByteBuffer.wrap(frames[1]).order(ByteOrder.LITTLE_ENDIAN).getShort(5).toInt() and 65535)
        assertEquals(Protocol.ACTION_UP, frames[1][9])
        assertThrows(IllegalArgumentException::class.java) { Protocol.packEvents(events) }
    }

    @Test fun invalidValuesCannotSerialize() {
        for (invalid in listOf(event.copy(action = 99), event.copy(toolType = 99),
                               event.copy(buttons = 8), event.copy(x = Float.NaN),
                               event.copy(pressure = Float.POSITIVE_INFINITY), event.copy(tiltX = 91f))) {
            assertThrows(IllegalArgumentException::class.java) { Protocol.packEvents(listOf(invalid)) }
        }
    }
}
