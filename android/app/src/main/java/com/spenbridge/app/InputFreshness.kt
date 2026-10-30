package com.spenbridge.app

/** MotionEvent uptime, rather than enqueue time, defines the capture boundary. */
class InputFreshness(private val maxAgeMillis: Long = 100) {
    enum class Result { FRESH, BEFORE_CAPTURE, STALE }
    private var epoch = 0L
    init { require(maxAgeMillis > 0) }
    fun reset(now: Long) { epoch = now }
    fun classify(oldest: Long, current: Long, now: Long): Result {
        if (current < oldest || current > now) return Result.STALE
        if (oldest < epoch) return Result.BEFORE_CAPTURE
        if (now - oldest > maxAgeMillis) return Result.STALE
        return Result.FRESH
    }
}
