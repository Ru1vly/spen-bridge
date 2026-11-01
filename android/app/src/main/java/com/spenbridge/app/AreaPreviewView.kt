package com.spenbridge.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat

/** Settings-only editor. Uses precisely the geometry used by input mapping. */
class AreaPreviewView(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    var mode = SettingsActivity.MODE_16_9
    var areaWidth = 100
    var areaHeight = 100
    var offsetX = 50
    var offsetY = 50
    var landscape = true
    var surfaceWidth = 0
    var surfaceHeight = 0
    var onEdit: ((Int, Int, Int, Int) -> Unit)? = null
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var gesture: AreaEditorGesture? = null
    private var activePointerId = -1
    private val density = resources.displayMetrics.density
    private fun tablet(): RectF {
        val metrics = resources.displayMetrics
        val sourceWidth = if (surfaceWidth > 0) surfaceWidth else metrics.widthPixels
        val sourceHeight = if (surfaceHeight > 0) surfaceHeight else metrics.heightPixels
        val drawLandscape = landscape || resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
        val ratio = if (drawLandscape) maxOf(sourceWidth, sourceHeight).toFloat() /
            minOf(sourceWidth, sourceHeight) else minOf(sourceWidth, sourceHeight).toFloat() / maxOf(sourceWidth, sourceHeight)
        val w = minOf(width - 32 * density, (height - 32 * density) * ratio).coerceAtLeast(1f)
        val h = w / ratio
        return RectF((width-w)/2, (height-h)/2, (width+w)/2, (height+h)/2)
    }
    private fun active(tablet: RectF): RectF {
        val r = TabletArea.calculate(tablet.width(), tablet.height(), mode, areaWidth, areaHeight, offsetX, offsetY)
        return RectF(tablet.left+r.left, tablet.top+r.top, tablet.left+r.left+r.width, tablet.top+r.top+r.height)
    }
    fun refresh() { invalidate() }
    override fun onDraw(canvas: Canvas) {
        val tablet = tablet()
        paint.style = Paint.Style.FILL
        paint.color = ContextCompat.getColor(context, R.color.surface_variant)
        canvas.drawRoundRect(tablet, 12*density, 12*density, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = density
        paint.color = ContextCompat.getColor(context, R.color.text_muted)
        canvas.drawRoundRect(tablet, 12*density, 12*density, paint)
        paint.style = Paint.Style.FILL
        val rect = active(tablet)
        paint.color = ContextCompat.getColor(context, R.color.primary)
        paint.alpha = 35
        canvas.drawRect(rect, paint)
        paint.alpha = 255
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 2*density
        canvas.drawRect(rect, paint)
        paint.style = Paint.Style.FILL
        if (mode != SettingsActivity.MODE_FULL) canvas.drawCircle(rect.right, rect.bottom, 7*density, paint)
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (mode == SettingsActivity.MODE_FULL) return false
        val tablet = tablet()
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val rect = active(tablet)
                val resizing = AreaEditorGesture.isResizeHandle(
                    TabletArea.Rect(rect.left, rect.top, rect.width(), rect.height()), event.x, event.y, 24*density)
                if (!resizing && !rect.contains(event.x,event.y)) return false
                activePointerId = event.getPointerId(0)
                gesture = AreaEditorGesture(tablet.width(), tablet.height(), mode,
                    AreaEditorGesture.Values(areaWidth, areaHeight, offsetX, offsetY),
                    event.x-tablet.left, event.y-tablet.top, resizing)
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(activePointerId)
                if (index < 0) { finishGesture(); return true }
                applyGesture(event.getX(index)-tablet.left, event.getY(index)-tablet.top)
            }
            MotionEvent.ACTION_UP -> {
                val index = event.findPointerIndex(activePointerId)
                if (index >= 0) applyGesture(event.getX(index)-tablet.left, event.getY(index)-tablet.top)
                finishGesture()
                performClick()
            }
            MotionEvent.ACTION_POINTER_UP -> {
                if (event.getPointerId(event.actionIndex) == activePointerId) finishGesture()
            }
            MotionEvent.ACTION_CANCEL -> finishGesture()
        }
        return true
    }

    private fun applyGesture(x: Float, y: Float) {
        val values = gesture?.move(x, y) ?: return
        areaWidth = values.width
        areaHeight = values.height
        offsetX = values.offsetX
        offsetY = values.offsetY
        onEdit?.invoke(areaWidth, areaHeight, offsetX, offsetY)
        invalidate()
    }

    private fun finishGesture() {
        gesture = null
        activePointerId = -1
        parent?.requestDisallowInterceptTouchEvent(false)
    }

    override fun performClick(): Boolean { super.performClick(); return true }
}
