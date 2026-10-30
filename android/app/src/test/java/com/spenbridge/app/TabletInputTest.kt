package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test

class TabletInputTest {
    @Test fun fullAreaIgnoresPersistedCropAndOffsets() {
        val area = TabletArea.calculate(1600f, 1000f, "full", 20, 30, 100, 0)
        assertEquals(TabletArea.Rect(0f, 0f, 1600f, 1000f), area)
    }

    @Test fun customAndAspectAreasRemainWithinSurface() {
        val custom = TabletArea.calculate(1000f, 1000f, "custom", 50, 20, 100, 0)
        assertEquals(TabletArea.Rect(500f, 0f, 500f, 200f), custom)
        val aspect = TabletArea.calculate(1600f, 1000f, "16:9")
        assertEquals(1600f, aspect.width, .01f)
        assertEquals(900f, aspect.height, .01f)
        assertEquals(50f, aspect.top, .01f)
    }

    @Test fun palmFirstDoesNotPreventStylusSelectionAndPointerUpNeverTransfersStroke() {
        val tracker = ActivePointerTracker()
        assertEquals(ActivePointerTracker.Selection.IGNORE, tracker.select(10, Protocol.TOOL_FINGER, false))
        assertEquals(ActivePointerTracker.Selection.START, tracker.select(22, Protocol.TOOL_STYLUS, false))
        assertEquals(22, tracker.current!!.id)
        assertFalse(tracker.finish(10))
        assertEquals(22, tracker.current!!.id)
        assertTrue(tracker.finish(22))
        assertNull(tracker.current)
    }

    @Test fun stylusPreemptsExplicitlyEnabledFingerAndResetNeedsFreshPointerDown() {
        val tracker = ActivePointerTracker()
        tracker.select(7, Protocol.TOOL_FINGER, true)
        assertEquals(ActivePointerTracker.Selection.PREEMPT, tracker.select(30, Protocol.TOOL_ERASER, true))
        assertEquals(30, tracker.current!!.id)
        assertEquals(ActivePointerTracker.Selection.IGNORE, tracker.select(7, Protocol.TOOL_FINGER, true))
        tracker.clear()
        assertNull(tracker.current)
    }

    @Test fun endpointValidationDoesNotExposePairingCode() {
        val endpoint = ConnectionEndpoint("localhost", 40118, "f".repeat(64), "a".repeat(43))
        assertFalse(endpoint.toString().contains(endpoint.code))
        for (host in listOf("127.0.0.1", "::1", "workstation.local", "b\u00fcro.local")) assertTrue(ConnectionEndpoint.validHost(host))
        for (host in listOf("", "http://pc", "pc:40118", "999.1.1.1", "host name", "host/path")) assertFalse(ConnectionEndpoint.validHost(host))
    }
}
