package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test

class SessionBufferTest {
    private val down = Protocol.Event(3, 0, 4, .5f, .5f, .5f)
    private val up = down.copy(action = Protocol.ACTION_UP, pressure = 0f, buttons = 0)

    @Test fun offlineAndOldSessionEventsNeverReplay() {
        val buffer = SessionBuffer()
        assertEquals(SessionBuffer.Offer.OFFLINE, buffer.offer(listOf(down)))
        buffer.begin(1)
        buffer.offer(listOf(down))
        buffer.clear()
        buffer.begin(2)
        assertNull(buffer.take(1))
        assertNull(buffer.take(2))
    }

    @Test fun overflowResetsInsteadOfDroppingAnUpTransition() {
        val buffer = SessionBuffer(capacity = 2)
        buffer.begin(1)
        buffer.offer(listOf(down, down.copy(action = Protocol.ACTION_MOVE)))
        assertEquals(SessionBuffer.Offer.RESET_REQUIRED, buffer.offer(listOf(up)))
        assertFalse(buffer.isActive(1))
        assertEquals(0, buffer.size())
        assertNull(buffer.take(1))
    }

    @Test fun allWithinBudgetTransitionsArePreserved() {
        val buffer = SessionBuffer()
        buffer.begin(1)
        val actions = listOf(down, down.copy(action = Protocol.ACTION_MOVE), up, down, up)
        for (event in actions) buffer.offer(listOf(event))
        assertEquals(actions, generateSequence { buffer.take(1)?.events }.flatten().toList())
    }

    @Test fun staleBatchInvalidatesTheSession() {
        var clock = 0L
        val buffer = SessionBuffer(maxAgeNanos = 100, clock = { clock })
        buffer.begin(1)
        buffer.offer(listOf(down))
        clock = 101
        assertThrows(SessionBuffer.StaleInputException::class.java) { buffer.take(1) }
        assertFalse(buffer.isActive(1))
        assertEquals(0, buffer.size())
    }
}
