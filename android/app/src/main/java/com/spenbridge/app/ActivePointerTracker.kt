package com.spenbridge.app

/** Pointer IDs are scoped to an input device. Only a pen may preempt a finger. */
class ActivePointerTracker {
    data class Pointer(val id: Int, val tool: Byte, val deviceId: Int = 0)
    enum class Selection { IGNORE, START, PREEMPT }
    var current: Pointer? = null
        private set

    fun select(id: Int, tool: Byte, allowFinger: Boolean, deviceId: Int = 0, newGesture: Boolean = false): Selection {
        if (tool !in listOf(Protocol.TOOL_STYLUS, Protocol.TOOL_ERASER, Protocol.TOOL_FINGER) ||
            (tool == Protocol.TOOL_FINGER && !allowFinger)) return Selection.IGNORE
        val previous = current
        if (previous != null) {
            val newOwnedGesture = newGesture && previous.deviceId == deviceId
            val penPreemptsFinger = previous.tool == Protocol.TOOL_FINGER && tool != Protocol.TOOL_FINGER
            if (!newOwnedGesture && !penPreemptsFinger) return Selection.IGNORE
        }
        current = Pointer(id, tool, deviceId)
        return if (previous == null) Selection.START else Selection.PREEMPT
    }

    fun finish(id: Int, deviceId: Int = 0): Boolean {
        if (current?.id != id || current?.deviceId != deviceId) return false
        current = null
        return true
    }

    fun clear() { current = null }
}
