package com.spenbridge.app

object TabletArea {
    data class Rect(val left: Float, val top: Float, val width: Float, val height: Float)
    fun calculate(width: Float, height: Float, mode: String, widthPercent: Int = 100,
                  heightPercent: Int = 100, offsetX: Int = 50, offsetY: Int = 50): Rect {
        val w = width.coerceAtLeast(1f)
        val h = height.coerceAtLeast(1f)
        if (mode == "full") return Rect(0f, 0f, w, h)
        val ratio = when (mode) { "16:10" -> 1.6f; "21:9" -> 21f / 9f; "16:9" -> 16f / 9f; else -> null }
        val baseW = if (ratio == null) w else minOf(w, h * ratio)
        val baseH = if (ratio == null) h else minOf(h, w / ratio)
        val activeW = baseW * widthPercent.coerceIn(20, 100) / 100f
        val activeH = baseH * heightPercent.coerceIn(20, 100) / 100f
        return Rect((w - activeW) * offsetX.coerceIn(0, 100) / 100f,
                    (h - activeH) * offsetY.coerceIn(0, 100) / 100f, activeW, activeH)
    }
}
