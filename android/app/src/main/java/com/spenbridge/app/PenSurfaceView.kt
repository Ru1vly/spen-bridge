package com.spenbridge.app

import android.content.Context
import androidx.core.content.ContextCompat
import android.graphics.Canvas
import android.graphics.RectF
import android.util.AttributeSet
import android.os.Build
import android.view.InputDevice
import android.view.PointerIcon
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

    var areaMode: AreaMode = AreaMode.FULL
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

    // Backward compatibility for matchAspectRatio
    var matchAspectRatio: Boolean
        get() = (areaMode == AreaMode.ASPECT_16_9)
        set(value) {
            areaMode = if (value) AreaMode.ASPECT_16_9 else AreaMode.FULL
            invalidate()
        }

    private var isHovering = false
    private val pointerTracker = ActivePointerTracker()
    private val freshness = InputFreshness().apply { reset(android.os.SystemClock.uptimeMillis()) }
    private var lastInputDevice: Int? = null
    private var lastSent = Protocol.Event(Protocol.ACTION_CANCEL, Protocol.TOOL_STYLUS, 0, 0f, 0f, 0f)
    private var callbackReceivedNanos = 0L

    init {
        setBackgroundColor(ContextCompat.getColor(context, R.color.canvas_bg))
        isFocusable = true
        contentDescription = context.getString(R.string.drawing_surface_description)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // A persistent source-class request also covers stylus hover, which
            // never produces ACTION_DOWN. Only this drawing view requests it.
            requestUnbufferedDispatch(InputDevice.SOURCE_CLASS_POINTER)
        }
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
            InputFreshness.Result.BEFORE_CAPTURE -> {
                InputTrace.rejected(oldest, event.eventTime, callbackReceivedNanos, event.historySize + 1, 1)
                false
            }
            InputFreshness.Result.STALE -> {
                InputTrace.rejected(oldest, event.eventTime, callbackReceivedNanos, event.historySize + 1, 2)
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

    override fun onResolvePointerIcon(event: MotionEvent, pointerIndex: Int): PointerIcon =
        PointerIcon.getSystemIcon(context, PointerIcon.TYPE_NULL)

    private fun eventRecord(event: MotionEvent, index: Int, action: Byte, rect: RectF, history: Int? = null): Protocol.Event {
        if (InputTrace.enabled && callbackReceivedNanos != 0L) {
            val precise = Build.VERSION.SDK_INT >= 34
            val sourceTime = if (precise) {
                if (history == null) event.eventTimeNanos else event.getHistoricalEventTimeNanos(history)
            } else {
                (if (history == null) event.eventTime else event.getHistoricalEventTime(history)) * 1000000L
            }
            InputTrace.sample(sourceTime, callbackReceivedNanos, precise, action)
        }
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

    override fun onTouchEvent(event: MotionEvent): Boolean {
        callbackReceivedNanos = if (InputTrace.enabled) System.nanoTime() else 0L
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
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) requestUnbufferedDispatch(event)
                if (selected == ActivePointerTracker.Selection.PREEMPT) cancelPrevious()
                // Hover-to-contact preserves held barrel switches and their rising edges.
                isHovering = false
                lastInputDevice = event.deviceId
                if (!send(listOf(eventRecord(event, actionIndex, Protocol.ACTION_DOWN, rect)))) return true
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
                send(events)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val active = pointerTracker.current ?: return true
                if (active.deviceId != event.deviceId || !acceptTiming(event)) return true
                if (pointerTracker.finish(event.getPointerId(actionIndex), event.deviceId)) {
                    lastInputDevice = event.deviceId
                    if (send(listOf(eventRecord(event, actionIndex, Protocol.ACTION_UP, rect)))) performClick()
                    parent?.requestDisallowInterceptTouchEvent(false)
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                val owner = pointerTracker.current?.deviceId ?: lastInputDevice
                if (owner != event.deviceId || !acceptTiming(event)) return true
                cancelInput()
            }
        }
        return true
    }

    override fun onHoverEvent(event: MotionEvent): Boolean {
        callbackReceivedNanos = if (InputTrace.enabled) System.nanoTime() else 0L
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
        val events = ArrayList<Protocol.Event>(event.historySize + 1)
        if (action == Protocol.ACTION_HOVER_MOVE) {
            for (history in 0 until event.historySize) events.add(eventRecord(event, index, action, rect, history))
        }
        events.add(eventRecord(event, index, action, rect))
        send(events)
        return true
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        callbackReceivedNanos = if (InputTrace.enabled) System.nanoTime() else 0L
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

        // Tablet mode is an input device. All visual feedback belongs in Settings.
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
