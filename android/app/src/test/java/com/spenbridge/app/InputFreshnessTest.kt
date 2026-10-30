package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test

class InputFreshnessTest {
    @Test fun captureResetRejectsPreviouslyQueuedDownAndHistory() {
        val timing = InputFreshness()
        timing.reset(1000)
        assertEquals(InputFreshness.Result.BEFORE_CAPTURE, timing.classify(999, 999, 1001))
        assertEquals(InputFreshness.Result.BEFORE_CAPTURE, timing.classify(999, 1001, 1002))
        assertEquals(InputFreshness.Result.FRESH, timing.classify(1000, 1001, 1002))
        timing.reset(1100)
        assertEquals(InputFreshness.Result.BEFORE_CAPTURE, timing.classify(1099, 1099, 1101))
    }
    @Test fun freshHeadDoesNotConcealStaleHistory() {
        val timing = InputFreshness()
        assertEquals(InputFreshness.Result.FRESH, timing.classify(200, 300, 300))
        assertEquals(InputFreshness.Result.STALE, timing.classify(199, 300, 300))
    }
    @Test fun impossibleTimeOrderingIsRejectedWithoutOverflow() {
        val timing = InputFreshness()
        assertEquals(InputFreshness.Result.STALE, timing.classify(201, 200, 300))
        assertEquals(InputFreshness.Result.STALE, timing.classify(200, 301, 300))
        assertEquals(InputFreshness.Result.STALE, timing.classify(200, Long.MAX_VALUE, 300))
        assertEquals(InputFreshness.Result.BEFORE_CAPTURE, timing.classify(Long.MIN_VALUE, 200, 300))
    }
    @Test fun reusedPointerIdFromAnotherDeviceCannotEndContact() {
        val tracker = ActivePointerTracker()
        tracker.select(0, Protocol.TOOL_STYLUS, true, deviceId = 11)
        assertEquals(ActivePointerTracker.Selection.IGNORE, tracker.select(0, Protocol.TOOL_FINGER, true, deviceId = 22, newGesture = true))
        assertFalse(tracker.finish(0, deviceId = 22))
        assertEquals(11, tracker.current!!.deviceId)
        assertTrue(tracker.finish(0, deviceId = 11))
    }
    @Test fun penPreemptionAcrossDevicesStillIgnoresTheOldFingerUp() {
        val tracker = ActivePointerTracker()
        tracker.select(0, Protocol.TOOL_FINGER, true, deviceId = 11)
        assertEquals(ActivePointerTracker.Selection.PREEMPT, tracker.select(0, Protocol.TOOL_ERASER, true, deviceId = 22))
        assertFalse(tracker.finish(0, deviceId = 11))
        assertTrue(tracker.finish(0, deviceId = 22))
    }
    @Test fun newGestureReplacesOnlyItsOwnDeviceContact() {
        val tracker = ActivePointerTracker()
        tracker.select(1, Protocol.TOOL_STYLUS, false, deviceId = 11)
        assertEquals(ActivePointerTracker.Selection.IGNORE, tracker.select(3, Protocol.TOOL_STYLUS, false, deviceId = 22, newGesture = true))
        assertEquals(ActivePointerTracker.Selection.PREEMPT, tracker.select(3, Protocol.TOOL_STYLUS, false, deviceId = 11, newGesture = true))
        assertEquals(3, tracker.current!!.id)
    }
}
