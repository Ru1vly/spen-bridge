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
            field = value.coerceIn(20, 100)
            invalidate()
        }

    var customHeightPercent: Int = 100
        set(value) {
            field = value.coerceIn(20, 100)
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
        textSize = android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP, 13f, resources.displayMetrics)
        typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
    }

    private val trailPath = Path()
    private var hoverX = -1f
    private var hoverY = -1f
    private var isHovering = false
    private val pointerTracker = ActivePointerTracker()
    private val freshness = InputFreshness().apply { reset(android.os.SystemClock.uptimeMillis()) }
    private var lastInputDevice: Int? = null
    private var lastSent = Protocol.Event(Protocol.ACTION_CANCEL, Protocol.TOOL_STYLUS, 0, 0f, 0f, 0f)
    private var trailSamples = 0

    init {
        isFocusable = true
        contentDescription = context.getString(R.string.drawing_surface_description)
    }

    fun getActiveRect(): RectF {
        val mode = when (areaMode) {
            AreaMode.FULL -> "full"
            AreaMode.CUSTOM -> "custom"
            AreaMode.ASPECT_16_10 -> "16:10"
            AreaMode.ASPECT_21_9 -> "21:9"
            else -> "16:9"
        }
        val rect = TabletArea.calculate(width.toFloat(), height.toFloat(), mode,
            customWidthPercent, customHeightPercent, customOffsetXPercent, customOffsetYPercent)
        return RectF(rect.left, rect.top, rect.left + rect.width, rect.top + rect.height)
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

    fun normalizeCoords(rawX: Float, rawY: Float): FloatPair {
        val rect = getActiveRect()
        val rw = rect.width().coerceAtLeast(1f)
        val rh = rect.height().coerceAtLeast(1f)
        val nx = ((rawX - rect.left) / rw).coerceIn(0f, 1f)
        val ny = ((rawY - rect.top) / rh).coerceIn(0f, 1f)
        return FloatPair(nx, ny)
    }

    private fun acceptedTool(event: MotionEvent, index: Int): Boolean = when (event.getToolType(index)) {
        MotionEvent.TOOL_TYPE_STYLUS, MotionEvent.TOOL_TYPE_ERASER -> true
        MotionEvent.TOOL_TYPE_FINGER -> !rejectFingerTouches
        else -> false
    }

    private fun send(events: List<Protocol.Event>): Boolean {
        if (events.any { !it.isValid() }) {
            cancelInput()
            sender?.resetSession()
            return false
        }
        if (events.isNotEmpty()) {
            lastSent = events.last()
            sender?.enqueueEvents(events)
        }
        return true
    }

    private fun hasReportedOutput(): Boolean = lastSent.buttons.toInt() != 0 ||
        (lastSent.action != Protocol.ACTION_CANCEL && lastSent.action != Protocol.ACTION_HOVER_EXIT)

    private fun acceptTiming(event: MotionEvent): Boolean {
        val oldest = if (event.historySize == 0) event.eventTime else event.getHistoricalEventTime(0)
        return when (freshness.classify(oldest, event.eventTime, android.os.SystemClock.uptimeMillis())) {
            InputFreshness.Result.FRESH -> true
            InputFreshness.Result.BEFORE_CAPTURE -> false
            InputFreshness.Result.STALE -> {
                val ownsOutput = pointerTracker.current?.deviceId == event.deviceId ||
                    (lastInputDevice == event.deviceId && hasReportedOutput())
                if (ownsOutput) {
                    cancelInput()
                    sender?.resetSession()
                }
                false
            }
        }
    }

    private fun cancelPrevious() {
        send(listOf(lastSent.copy(action = Protocol.ACTION_CANCEL, buttons = 0, pressure = 0f)))
    }

    fun cancelInput() {
        freshness.reset(android.os.SystemClock.uptimeMillis())
        if (pointerTracker.current != null || isHovering || hasReportedOutput()) cancelPrevious()
        lastInputDevice = null
        parent?.requestDisallowInterceptTouchEvent(false)
        pointerTracker.clear()
        isHovering = false
        hoverX = -1f
        hoverY = -1f
        trailPath.reset()
        trailSamples = 0
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        if (oldw != 0 && oldh != 0) cancelInput()
    }

    override fun onDetachedFromWindow() {
        cancelInput()
        super.onDetachedFromWindow()
    }

    override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
        super.onWindowFocusChanged(hasWindowFocus)
        cancelInput()
    }

    override fun performClick(): Boolean = super.performClick()

    private fun eventRecord(event: MotionEvent, index: Int, action: Byte, rect: RectF, history: Int? = null): Protocol.Event {
        val rawX = if (history == null) event.getX(index) else event.getHistoricalX(index, history)
        val rawY = if (history == null) event.getY(index) else event.getHistoricalY(index, history)
        val pressure = if (history == null) event.getPressure(index) else event.getHistoricalPressure(index, history)
        val (tiltX, tiltY) = getTiltDegrees(event, index, history)
        val contact = action == Protocol.ACTION_DOWN || action == Protocol.ACTION_MOVE
        val buttons = getProtocolButtons(event.buttonState).toInt() or if (contact) Protocol.BUTTON_TOUCH.toInt() else 0
        return Protocol.Event(action, getProtocolToolType(event.getToolType(index)), buttons.toShort(),
            if (rawX.isFinite()) ((rawX - rect.left) / rect.width().coerceAtLeast(1f)).coerceIn(0f, 1f) else Float.NaN,
            if (rawY.isFinite()) ((rawY - rect.top) / rect.height().coerceAtLeast(1f)).coerceIn(0f, 1f) else Float.NaN,
            if (!pressure.isFinite()) Float.NaN else if (contact) pressure.coerceIn(0f, 1f) else 0f, tiltX, tiltY)
    }

    private fun appendTrail(x: Float, y: Float, beginning: Boolean) {
        if (!showLocalPreview) return
        if (beginning || trailSamples >= 4096) {
            trailPath.reset()
            trailPath.moveTo(x, y)
            trailSamples = 1
        } else {
            trailPath.lineTo(x, y)
            trailSamples++
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val actionIndex = event.actionIndex
        val rect = getActiveRect()
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                if (!acceptedTool(event, actionIndex)) return true
                val tool = getProtocolToolType(event.getToolType(actionIndex))
                val active = pointerTracker.current
                if (active != null && active.deviceId != event.deviceId &&
                    !(active.tool == Protocol.TOOL_FINGER && tool != Protocol.TOOL_FINGER)) return true
                if (!acceptTiming(event)) return true
                val selected = pointerTracker.select(event.getPointerId(actionIndex), tool,
                    !rejectFingerTouches, event.deviceId, event.actionMasked == MotionEvent.ACTION_DOWN)
                if (selected == ActivePointerTracker.Selection.IGNORE) return true
                if (selected == ActivePointerTracker.Selection.PREEMPT) cancelPrevious()
                // Hover-to-contact preserves held barrel switches and their rising edges.
                isHovering = false
                lastInputDevice = event.deviceId
                if (!send(listOf(eventRecord(event, actionIndex, Protocol.ACTION_DOWN, rect)))) return true
                appendTrail(event.getX(actionIndex), event.getY(actionIndex), true)
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE -> {
                val active = pointerTracker.current ?: return true
                if (active.deviceId != event.deviceId || !acceptTiming(event)) return true
                val index = event.findPointerIndex(active.id)
                if (index < 0 || !acceptedTool(event, index)) { cancelInput(); return true }
                val events = ArrayList<Protocol.Event>(event.historySize + 1)
                for (history in 0 until event.historySize) events.add(eventRecord(event, index, Protocol.ACTION_MOVE, rect, history))
                events.add(eventRecord(event, index, Protocol.ACTION_MOVE, rect))
                lastInputDevice = event.deviceId
                if (send(events)) {
                    for (history in 0 until event.historySize) appendTrail(event.getHistoricalX(index, history), event.getHistoricalY(index, history), false)
                    appendTrail(event.getX(index), event.getY(index), false)
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val active = pointerTracker.current ?: return true
                if (active.deviceId != event.deviceId || !acceptTiming(event)) return true
                if (pointerTracker.finish(event.getPointerId(actionIndex), event.deviceId)) {
                    lastInputDevice = event.deviceId
                    if (send(listOf(eventRecord(event, actionIndex, Protocol.ACTION_UP, rect)))) performClick()
                    trailPath.reset()
                    trailSamples = 0
                    parent?.requestDisallowInterceptTouchEvent(false)
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                val owner = pointerTracker.current?.deviceId ?: lastInputDevice
                if (owner != event.deviceId || !acceptTiming(event)) return true
                cancelInput()
            }
        }
        postInvalidateOnAnimation()
        return true
    }

    override fun onHoverEvent(event: MotionEvent): Boolean {
        if (pointerTracker.current != null) return true
        val index = (0 until event.pointerCount).firstOrNull { acceptedTool(event, it) } ?: return false
        if (!acceptTiming(event)) return true
        val rect = getActiveRect()
        val action = when (event.actionMasked) {
            MotionEvent.ACTION_HOVER_ENTER -> Protocol.ACTION_HOVER_ENTER
            MotionEvent.ACTION_HOVER_MOVE -> Protocol.ACTION_HOVER_MOVE
            MotionEvent.ACTION_HOVER_EXIT -> Protocol.ACTION_HOVER_EXIT
            else -> return super.onHoverEvent(event)
        }
        lastInputDevice = event.deviceId
        isHovering = action != Protocol.ACTION_HOVER_EXIT
        hoverX = if (isHovering) event.getX(index) else -1f
        hoverY = if (isHovering) event.getY(index) else -1f
        val events = ArrayList<Protocol.Event>(event.historySize + 1)
        if (action == Protocol.ACTION_HOVER_MOVE) {
            for (history in 0 until event.historySize) events.add(eventRecord(event, index, action, rect, history))
        }
        events.add(eventRecord(event, index, action, rect))
        send(events)
        postInvalidateOnAnimation()
        return true
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.actionMasked != MotionEvent.ACTION_BUTTON_PRESS && event.actionMasked != MotionEvent.ACTION_BUTTON_RELEASE) {
            return super.onGenericMotionEvent(event)
        }
        val active = pointerTracker.current
        if (active != null && active.deviceId != event.deviceId) return true
        val index = if (active == null) (0 until event.pointerCount).firstOrNull { acceptedTool(event, it) }
                    else event.findPointerIndex(active.id).takeIf { it >= 0 && acceptedTool(event, it) }
        if (index == null) return false
        if (!acceptTiming(event)) return true
        lastInputDevice = event.deviceId
        if (active == null) isHovering = true
        send(listOf(eventRecord(event, index, if (active == null) Protocol.ACTION_HOVER_MOVE else Protocol.ACTION_MOVE, getActiveRect())))
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
                    AreaMode.FULL -> context.getString(R.string.hud_area_full)
                    AreaMode.ASPECT_16_9 -> context.getString(R.string.hud_area_aspect, "16:9")
                    AreaMode.ASPECT_16_10 -> context.getString(R.string.hud_area_aspect, "16:10")
                    AreaMode.ASPECT_21_9 -> context.getString(R.string.hud_area_aspect, "21:9")
                    AreaMode.CUSTOM -> context.getString(R.string.hud_area_custom, customWidthPercent, customHeightPercent)
                }
                val labelInset = 8f * resources.displayMetrics.density
                canvas.drawText(modeLabel, rect.left + labelInset, rect.top + labelInset - labelPaint.ascent(), labelPaint)
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

    private fun getTiltDegrees(event: MotionEvent, index: Int, history: Int? = null): FloatPair {
        fun axis(which: Int): Float = if (history == null) event.getAxisValue(which, index)
                                     else event.getHistoricalAxisValue(which, index, history)
        val tiltRad = axis(MotionEvent.AXIS_TILT)
        val orientRad = axis(MotionEvent.AXIS_ORIENTATION)
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
