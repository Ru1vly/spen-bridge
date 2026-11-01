package com.spenbridge.app

import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.roundToInt

/** Geometry for one edit, in tablet-local pixels. Quantization never feeds back into the gesture. */
class AreaEditorGesture(
    private val tabletWidth: Float,
    private val tabletHeight: Float,
    private val mode: String,
    private val initial: Values,
    private val downX: Float,
    private val downY: Float,
    private val resizing: Boolean
) {
    data class Values(val width: Int, val height: Int, val offsetX: Int, val offsetY: Int)

    companion object {
        fun isResizeHandle(rect: TabletArea.Rect, x: Float, y: Float, radius: Float): Boolean {
            // A tiny area must still have a central drag target, even inside the handle's hit region.
            val center = x in (rect.left + rect.width * .25f)..(rect.left + rect.width * .75f) &&
                y in (rect.top + rect.height * .25f)..(rect.top + rect.height * .75f)
            return !center && abs(x - rect.left - rect.width) < radius &&
                abs(y - rect.top - rect.height) < radius
        }
    }


    private val start = TabletArea.calculate(tabletWidth, tabletHeight, mode,
        initial.width, initial.height, initial.offsetX, initial.offsetY)
    private val base = TabletArea.calculate(tabletWidth, tabletHeight, mode)

    fun move(x: Float, y: Float): Values {
        if (mode == "full") return initial
        val dx = x - downX
        val dy = y - downY
        if (!resizing) return initial.copy(
            offsetX = position(start.left + dx, tabletWidth - start.width, initial.offsetX),
            offsetY = position(start.top + dy, tabletHeight - start.height, initial.offsetY))

        // Preserve the grab offset inside the handle, so the first move never jumps.
        val candidateWidth = (start.width + dx) / base.width * 100f
        val candidateHeight = (start.height + dy) / base.height * 100f
        val maxWidth = maximumSize(tabletWidth - start.left, base.width)
        val maxHeight = maximumSize(tabletHeight - start.top, base.height)
        val width: Int
        val height: Int
        if (mode == "custom") {
            width = candidateWidth.roundToInt().coerceIn(20, maxWidth)
            height = candidateHeight.roundToInt().coerceIn(20, maxHeight)
        } else {
            val scale = if (abs(candidateWidth - initial.width) >= abs(candidateHeight - initial.height))
                candidateWidth else candidateHeight
            width = scale.roundToInt().coerceIn(20, minOf(maxWidth, maxHeight))
            height = width
        }
        val resized = TabletArea.calculate(tabletWidth, tabletHeight, mode, width, height)
        return Values(width, height,
            position(start.left, tabletWidth - resized.width, initial.offsetX),
            position(start.top, tabletHeight - resized.height, initial.offsetY))
    }

    private fun maximumSize(available: Float, base: Float): Int =
        floor(available / base * 100f + .001f).toInt().coerceIn(20, 100)

    private fun position(pixel: Float, available: Float, fallback: Int): Int =
        if (available > 1f) (pixel / available * 100f).roundToInt().coerceIn(0, 100)
        else fallback.coerceIn(0, 100)
}
