package com.spenonlinux.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

class PenSurfaceView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    var sender: PenEventSender? = null
    var rejectFingerTouches: Boolean = true
    var showLocalPreview: Boolean = true

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

    private val trailPath = Path()
    private var hoverX = -1f
    private var hoverY = -1f
    private var isHovering = false

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val toolType = getProtocolToolType(event.getToolType(0))
        if (rejectFingerTouches && toolType == Protocol.TOOL_FINGER) {
            return false
        }

        val buttons = getProtocolButtons(event.buttonState)
        val (tiltX, tiltY) = getTiltDegrees(event)

        val w = width.toFloat().coerceAtLeast(1f)
        val h = height.toFloat().coerceAtLeast(1f)

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val normX = (event.x / w).coerceIn(0f, 1f)
                val normY = (event.y / h).coerceIn(0f, 1f)
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
                    val histX = (event.getHistoricalX(0, i) / w).coerceIn(0f, 1f)
                    val histY = (event.getHistoricalY(0, i) / h).coerceIn(0f, 1f)
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

                val currentNormX = (event.x / w).coerceIn(0f, 1f)
                val currentNormY = (event.y / h).coerceIn(0f, 1f)
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
                val normX = (event.x / w).coerceIn(0f, 1f)
                val normY = (event.y / h).coerceIn(0f, 1f)

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

        val w = width.toFloat().coerceAtLeast(1f)
        val h = height.toFloat().coerceAtLeast(1f)
        val normX = (event.x / w).coerceIn(0f, 1f)
        val normY = (event.y / h).coerceIn(0f, 1f)

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
                sender?.enqueueEvents(
                    listOf(
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
                )
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

    private fun getTiltDegrees(event: MotionEvent): Pair<Float, Float> {
        val tiltRad = event.getAxisValue(MotionEvent.AXIS_TILT)
        val orientRad = event.getAxisValue(MotionEvent.AXIS_ORIENTATION)
        var tx = 0f
        var ty = 0f
        if (tiltRad > 0f) {
            val tiltDeg = Math.toDegrees(tiltRad.toDouble()).toFloat()
            tx = (tiltDeg * Math.sin(orientRad.toDouble())).toFloat()
            ty = (-tiltDeg * Math.cos(orientRad.toDouble())).toFloat()
        }
        return Pair(tx.coerceIn(-90f, 90f), ty.coerceIn(-90f, 90f))
    }
}
