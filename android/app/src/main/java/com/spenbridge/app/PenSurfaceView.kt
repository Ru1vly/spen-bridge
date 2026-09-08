package com.spenbridge.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

class PenSurfaceView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    enum class AreaMode {
        FULL,
        ASPECT_16_9,
        ASPECT_16_10,
        ASPECT_21_9,
        CUSTOM
    }

    var sender: PenEventSender? = null
    var rejectFingerTouches: Boolean = true
    var showLocalPreview: Boolean = true

    var areaMode: AreaMode = AreaMode.ASPECT_16_9
        set(value) {
            field = value
            invalidate()
        }

    var customWidthPercent: Int = 100
        set(value) {
            field = value.coerceIn(10, 100)
            invalidate()
        }

    var customHeightPercent: Int = 100
        set(value) {
            field = value.coerceIn(10, 100)
            invalidate()
        }

    var customOffsetXPercent: Int = 50
        set(value) {
            field = value.coerceIn(0, 100)
            invalidate()
        }

    var customOffsetYPercent: Int = 50
        set(value) {
            field = value.coerceIn(0, 100)
            invalidate()
        }

    var showAreaBorder: Boolean = true
        set(value) {
            field = value
            invalidate()
        }

    var showAreaShading: Boolean = true
        set(value) {
            field = value
            invalidate()
        }

    // Backward compatibility for matchAspectRatio
    var matchAspectRatio: Boolean
        get() = (areaMode == AreaMode.ASPECT_16_9)
        set(value) {
            areaMode = if (value) AreaMode.ASPECT_16_9 else AreaMode.FULL
            invalidate()
        }

    private val trailPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF00E5FF.toInt()
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = 4f
    }

    private val hoverPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x8000E5FF.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }

    private val aspectFramePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x4400E5FF.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }

    private val cornerBracketPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF00E5FF.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 4f
        strokeCap = Paint.Cap.SQUARE
    }

    private val aspectShadePaint = Paint().apply {
        color = 0x880C0D12.toInt()
        style = Paint.Style.FILL
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x80FFFFFF.toInt()
        textSize = 26f
        typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
    }

    private val trailPath = Path()
    private var hoverX = -1f
    private var hoverY = -1f
    private var isHovering = false

    fun getActiveRect(): RectF {
        val w = width.toFloat().coerceAtLeast(1f)
        val h = height.toFloat().coerceAtLeast(1f)

        val (baseW, baseH) = when (areaMode) {
            AreaMode.FULL -> FloatPair(w, h)
            AreaMode.ASPECT_16_9 -> computeAspectFit(w, h, 16f / 9f)
            AreaMode.ASPECT_16_10 -> computeAspectFit(w, h, 16f / 10f)
            AreaMode.ASPECT_21_9 -> computeAspectFit(w, h, 21f / 9f)
            AreaMode.CUSTOM -> {
                val cw = w * (customWidthPercent.coerceIn(10, 100) / 100f)
                val ch = h * (customHeightPercent.coerceIn(10, 100) / 100f)
                FloatPair(cw, ch)
            }
        }

        val activeW = if (areaMode != AreaMode.CUSTOM && customWidthPercent < 100) {
            baseW * (customWidthPercent.coerceIn(10, 100) / 100f)
        } else {
            baseW
        }

        val activeH = if (areaMode != AreaMode.CUSTOM && customHeightPercent < 100) {
            baseH * (customHeightPercent.coerceIn(10, 100) / 100f)
        } else {
            baseH
        }

        val maxOffsetX = (w - activeW).coerceAtLeast(0f)
        val maxOffsetY = (h - activeH).coerceAtLeast(0f)

        val left = maxOffsetX * (customOffsetXPercent.coerceIn(0, 100) / 100f)
        val top = maxOffsetY * (customOffsetYPercent.coerceIn(0, 100) / 100f)

        return RectF(left, top, left + activeW, top + activeH)
    }

    /**
     * Zero-boxing stand-in for Pair<Float, Float>. A generic Pair stores its
     * fields as boxed Any?, allocating on every call; this packs both floats'
     * raw bits into one Long so the JVM inline-class erases to a bare long
     * with no allocation, matching a normal function return.
     */
    @JvmInline
    value class FloatPair(private val packed: Long) {
        constructor(x: Float, y: Float) : this(
            (x.toRawBits().toLong() shl 32) or (y.toRawBits().toLong() and 0xFFFFFFFFL)
        )

        val x: Float get() = Float.fromBits((packed ushr 32).toInt())
        val y: Float get() = Float.fromBits(packed.toInt())

        operator fun component1(): Float = x
        operator fun component2(): Float = y
    }

    private fun computeAspectFit(w: Float, h: Float, targetAspect: Float): FloatPair {
        val currentAspect = w / h
        return if (currentAspect > targetAspect) {
            FloatPair(h * targetAspect, h)
        } else {
            FloatPair(w, w / targetAspect)
        }
    }

    fun normalizeCoords(rawX: Float, rawY: Float): FloatPair {
        val rect = getActiveRect()
        val rw = rect.width().coerceAtLeast(1f)
        val rh = rect.height().coerceAtLeast(1f)
        val nx = ((rawX - rect.left) / rw).coerceIn(0f, 1f)
        val ny = ((rawY - rect.top) / rh).coerceIn(0f, 1f)
        return FloatPair(nx, ny)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val toolType = getProtocolToolType(event.getToolType(0))
        if (rejectFingerTouches && toolType == Protocol.TOOL_FINGER) {
            return false
        }

        val buttons = getProtocolButtons(event.buttonState)
        val (tiltX, tiltY) = getTiltDegrees(event)

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val (normX, normY) = normalizeCoords(event.x, event.y)
                val pressure = event.pressure.coerceIn(0f, 1f)

                if (showLocalPreview) {
                    trailPath.reset()
                    trailPath.moveTo(event.x, event.y)
                    invalidate()
                }

                sender?.enqueueEvents(
                    listOf(
                        Protocol.Event(
                            action = Protocol.ACTION_DOWN,
                            toolType = toolType,
                            buttons = (buttons.toInt() or Protocol.BUTTON_TOUCH.toInt()).toShort(),
                            x = normX,
                            y = normY,
                            pressure = pressure,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                )
            }

            MotionEvent.ACTION_MOVE -> {
                val historySize = event.historySize
                val events = ArrayList<Protocol.Event>(historySize + 1)

                for (i in 0 until historySize) {
                    val (histX, histY) = normalizeCoords(event.getHistoricalX(0, i), event.getHistoricalY(0, i))
                    val histP = event.getHistoricalPressure(0, i).coerceIn(0f, 1f)

                    if (showLocalPreview) {
                        trailPath.lineTo(event.getHistoricalX(0, i), event.getHistoricalY(0, i))
                    }

                    events.add(
                        Protocol.Event(
                            action = Protocol.ACTION_MOVE,
                            toolType = toolType,
                            buttons = (buttons.toInt() or Protocol.BUTTON_TOUCH.toInt()).toShort(),
                            x = histX,
                            y = histY,
                            pressure = histP,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                }

                val (currentNormX, currentNormY) = normalizeCoords(event.x, event.y)
                val currentP = event.pressure.coerceIn(0f, 1f)

                if (showLocalPreview) {
                    trailPath.lineTo(event.x, event.y)
                    invalidate()
                }

                events.add(
                    Protocol.Event(
                        action = Protocol.ACTION_MOVE,
                        toolType = toolType,
                        buttons = (buttons.toInt() or Protocol.BUTTON_TOUCH.toInt()).toShort(),
                        x = currentNormX,
                        y = currentNormY,
                        pressure = currentP,
                        tiltX = tiltX,
                        tiltY = tiltY
                    )
                )

                sender?.enqueueEvents(events)
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val (normX, normY) = normalizeCoords(event.x, event.y)

                if (showLocalPreview) {
                    trailPath.reset()
                    invalidate()
                }

                sender?.enqueueEvents(
                    listOf(
                        Protocol.Event(
                            action = if (event.actionMasked == MotionEvent.ACTION_UP) Protocol.ACTION_UP else Protocol.ACTION_CANCEL,
                            toolType = toolType,
                            buttons = buttons,
                            x = normX,
                            y = normY,
                            pressure = 0f,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                )
            }
        }

        return true
    }

    override fun onHoverEvent(event: MotionEvent): Boolean {
        val toolType = getProtocolToolType(event.getToolType(0))
        if (rejectFingerTouches && toolType == Protocol.TOOL_FINGER) {
            return false
        }

        val buttons = getProtocolButtons(event.buttonState)
        val (tiltX, tiltY) = getTiltDegrees(event)

        val (normX, normY) = normalizeCoords(event.x, event.y)

        when (event.actionMasked) {
            MotionEvent.ACTION_HOVER_ENTER -> {
                isHovering = true
                hoverX = event.x
                hoverY = event.y
                invalidate()
                sender?.enqueueEvents(
                    listOf(
                        Protocol.Event(
                            action = Protocol.ACTION_HOVER_ENTER,
                            toolType = toolType,
                            buttons = buttons,
                            x = normX,
                            y = normY,
                            pressure = 0f,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                )
            }

            MotionEvent.ACTION_HOVER_MOVE -> {
                isHovering = true
                hoverX = event.x
                hoverY = event.y
                invalidate()

                // Drain batched historical samples the same way ACTION_MOVE
                // does above - Android exposes event.historySize for
                // hover-generated MotionEvents too. Without this, the
                // cursor-preview position sent while hovering (before
                // touchdown) was silently capped to the UI thread's
                // callback/batching cadence (~60-120Hz) instead of the full
                // digitizer sampling rate the touch path already carries
                // through.
                val historySize = event.historySize
                val events = ArrayList<Protocol.Event>(historySize + 1)

                for (i in 0 until historySize) {
                    val (histX, histY) = normalizeCoords(event.getHistoricalX(0, i), event.getHistoricalY(0, i))
                    events.add(
                        Protocol.Event(
                            action = Protocol.ACTION_HOVER_MOVE,
                            toolType = toolType,
                            buttons = buttons,
                            x = histX,
                            y = histY,
                            pressure = 0f,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                }

                events.add(
                    Protocol.Event(
                        action = Protocol.ACTION_HOVER_MOVE,
                        toolType = toolType,
                        buttons = buttons,
                        x = normX,
                        y = normY,
                        pressure = 0f,
                        tiltX = tiltX,
                        tiltY = tiltY
                    )
                )

                sender?.enqueueEvents(events)
            }

            MotionEvent.ACTION_HOVER_EXIT -> {
                isHovering = false
                hoverX = -1f
                hoverY = -1f
                invalidate()
                sender?.enqueueEvents(
                    listOf(
                        Protocol.Event(
                            action = Protocol.ACTION_HOVER_EXIT,
                            toolType = toolType,
                            buttons = buttons,
                            x = normX,
                            y = normY,
                            pressure = 0f,
                            tiltX = tiltX,
                            tiltY = tiltY
                        )
                    )
                )
            }
        }

        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val rect = getActiveRect()
        val w = width.toFloat()
        val h = height.toFloat()

        val isRestricted = (rect.width() < w - 4f || rect.height() < h - 4f || rect.left > 2f || rect.top > 2f)

        if (isRestricted) {
            if (showAreaShading) {
                // Shade left margin
                if (rect.left > 0f) {
                    canvas.drawRect(0f, 0f, rect.left, h, aspectShadePaint)
                }
                // Shade right margin
                if (rect.right < w) {
                    canvas.drawRect(rect.right, 0f, w, h, aspectShadePaint)
                }
                // Shade top margin
                if (rect.top > 0f) {
                    canvas.drawRect(rect.left, 0f, rect.right, rect.top, aspectShadePaint)
                }
                // Shade bottom margin
                if (rect.bottom < h) {
                    canvas.drawRect(rect.left, rect.bottom, rect.right, h, aspectShadePaint)
                }
            }

            if (showAreaBorder) {
                // Draw active frame boundary
                canvas.drawRect(rect, aspectFramePaint)

                // Draw corner brackets
                val bLen = 28f
                // Top-Left
                canvas.drawLine(rect.left, rect.top, rect.left + bLen, rect.top, cornerBracketPaint)
                canvas.drawLine(rect.left, rect.top, rect.left, rect.top + bLen, cornerBracketPaint)
                // Top-Right
                canvas.drawLine(rect.right, rect.top, rect.right - bLen, rect.top, cornerBracketPaint)
                canvas.drawLine(rect.right, rect.top, rect.right, rect.top + bLen, cornerBracketPaint)
                // Bottom-Left
                canvas.drawLine(rect.left, rect.bottom, rect.left + bLen, rect.bottom, cornerBracketPaint)
                canvas.drawLine(rect.left, rect.bottom, rect.left, rect.bottom - bLen, cornerBracketPaint)
                // Bottom-Right
                canvas.drawLine(rect.right, rect.bottom, rect.right - bLen, rect.bottom, cornerBracketPaint)
                canvas.drawLine(rect.right, rect.bottom, rect.right, rect.bottom - bLen, cornerBracketPaint)

                // Label
                val modeLabel = when (areaMode) {
                    AreaMode.FULL -> "Full Surface"
                    AreaMode.ASPECT_16_9 -> "16:9 Active Area"
                    AreaMode.ASPECT_16_10 -> "16:10 Active Area"
                    AreaMode.ASPECT_21_9 -> "21:9 Active Area"
                    AreaMode.CUSTOM -> "Custom Area (${customWidthPercent}% × ${customHeightPercent}%)"
                }
                canvas.drawText(modeLabel, rect.left + 16f, rect.top + 34f, labelPaint)
            }
        }

        if (showLocalPreview && !trailPath.isEmpty) {
            canvas.drawPath(trailPath, trailPaint)
        }

        if (isHovering && hoverX >= 0 && hoverY >= 0) {
            canvas.drawCircle(hoverX, hoverY, 12f, hoverPaint)
        }
    }

    private fun getProtocolToolType(androidToolType: Int): Byte {
        return when (androidToolType) {
            MotionEvent.TOOL_TYPE_ERASER -> Protocol.TOOL_ERASER
            MotionEvent.TOOL_TYPE_STYLUS -> Protocol.TOOL_STYLUS
            else -> Protocol.TOOL_FINGER
        }
    }

    private fun getProtocolButtons(buttonState: Int): Short {
        var buttons: Short = 0
        if ((buttonState and MotionEvent.BUTTON_STYLUS_PRIMARY) != 0) {
            buttons = (buttons.toInt() or Protocol.BUTTON_STYLUS.toInt()).toShort()
        }
        if ((buttonState and MotionEvent.BUTTON_STYLUS_SECONDARY) != 0) {
            buttons = (buttons.toInt() or Protocol.BUTTON_STYLUS2.toInt()).toShort()
        }
        return buttons
    }

    private fun getTiltDegrees(event: MotionEvent): FloatPair {
        val tiltRad = event.getAxisValue(MotionEvent.AXIS_TILT)
        val orientRad = event.getAxisValue(MotionEvent.AXIS_ORIENTATION)
        var tx = 0f
        var ty = 0f
        if (tiltRad > 0f) {
            val tiltDeg = Math.toDegrees(tiltRad.toDouble()).toFloat()
            tx = (tiltDeg * Math.sin(orientRad.toDouble())).toFloat()
            ty = (-tiltDeg * Math.cos(orientRad.toDouble())).toFloat()
        }
        return FloatPair(tx.coerceIn(-90f, 90f), ty.coerceIn(-90f, 90f))
    }
}
