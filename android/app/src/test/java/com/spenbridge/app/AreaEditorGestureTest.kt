package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test

class AreaEditorGestureTest {
    private val initial = AreaEditorGesture.Values(50, 50, 50, 50)

    @Test fun smallAreasKeepADragTargetSeparateFromTheResizeCorner() {
        val tiny = TabletArea.Rect(0f, 0f, 16f, 25.6f)
        assertFalse(AreaEditorGesture.isResizeHandle(tiny, 8f, 12.8f, 24f))
        assertTrue(AreaEditorGesture.isResizeHandle(tiny, 16f, 25.6f, 24f))
        val large = TabletArea.Rect(100f, 200f, 200f, 100f)
        assertFalse(AreaEditorGesture.isResizeHandle(large, 200f, 250f, 24f))
        assertTrue(AreaEditorGesture.isResizeHandle(large, 320f, 320f, 24f))
        assertFalse(AreaEditorGesture.isResizeHandle(large, 340f, 340f, 24f))
    }

    @Test fun slowDragAccumulatesAndMatchesOneLargeMove() {
        val gesture = AreaEditorGesture(1000f, 1000f, "custom", initial, 500f, 500f, false)
        var slow = initial
        for (pixel in 1..100) slow = gesture.move(500f + pixel, 500f)
        assertEquals(gesture.move(600f, 500f), slow)
        assertEquals(70, slow.offsetX)
        assertEquals(50, slow.offsetY)
    }

    @Test fun grabbingNearTheResizeCornerDoesNotJumpOnFirstMove() {
        val gesture = AreaEditorGesture(1000f, 1000f, "custom", initial, 770f, 765f, true)
        assertEquals(initial, gesture.move(770f, 765f))
        val resized = gesture.move(870f, 865f)
        assertEquals(60, resized.width)
        assertEquals(60, resized.height)
    }

    @Test fun movingTheHandleVerticallyResizesBothDimensionsForFixedRatios() {
        val gesture = AreaEditorGesture(1000f, 1000f, "16:9",
            AreaEditorGesture.Values(60, 60, 50, 50), 800f, 668.75f, true)
        val resized = gesture.move(800f, 725f)
        assertEquals(70, resized.width)
        assertEquals(70, resized.height)
        val rect = TabletArea.calculate(1000f, 1000f, "16:9",
            resized.width, resized.height, resized.offsetX, resized.offsetY)
        assertEquals(16f / 9f, rect.width / rect.height, .001f)
    }

    @Test fun resizingToTheEdgePreservesTheOppositeCornerAndStaysInside() {
        val gesture = AreaEditorGesture(1000f, 1000f, "custom", initial, 750f, 750f, true)
        val resized = gesture.move(2000f, 2000f)
        assertEquals(AreaEditorGesture.Values(75, 75, 100, 100), resized)
        val rect = TabletArea.calculate(1000f, 1000f, "custom",
            resized.width, resized.height, resized.offsetX, resized.offsetY)
        assertEquals(TabletArea.Rect(250f, 250f, 750f, 750f), rect)
    }

    @Test fun dragAndResizeClampAcrossRatiosAndTabletOrientations() {
        for ((w, h) in listOf(1000f to 1600f, 1600f to 1000f)) {
            for (mode in listOf("full", "custom", "16:9", "16:10", "21:9")) {
                for (resize in listOf(false, true)) {
                    val gesture = AreaEditorGesture(w, h, mode, initial, w/2, h/2, resize)
                    for ((x, y) in listOf(-10000f to -10000f, 10000f to 10000f)) {
                        val values = gesture.move(x, y)
                        val rect = TabletArea.calculate(w, h, mode,
                            values.width, values.height, values.offsetX, values.offsetY)
                        assertTrue(rect.left >= 0 && rect.top >= 0)
                        assertTrue(rect.left + rect.width <= w + .01f)
                        assertTrue(rect.top + rect.height <= h + .01f)
                        assertTrue(values.width in 20..100 && values.height in 20..100)
                        if (mode == "full") assertEquals(initial, values)
                    }
                }
            }
        }
    }
}
