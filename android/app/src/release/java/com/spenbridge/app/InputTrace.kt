@file:Suppress("UNUSED_PARAMETER", "NOTHING_TO_INLINE")
package com.spenbridge.app

/** Compile-time no-ops: normal release forwarding has no trace clock/CRC work. */
object InputTrace {
    const val enabled = false
    inline fun sample(sourceNanos: Long, callbackNanos: Long, precise: Boolean, action: Byte) {}
    inline fun rejected(oldestMillis: Long, currentMillis: Long, callback: Long, count: Int, reason: Int) {}
    inline fun queueReset(session: Long, count: Int, reason: Int) {}
    inline fun state(session: Long, state: Int) {}
    inline fun queued(session: Long, count: Int) {}
    inline fun heartbeat(session: Long, sequence: Short, began: Long, written: Long, received: Long) {}
    inline fun packet(session: Long, sequence: Short, count: Int, bytes: ByteArray, size: Int,
                      created: Long, began: Long, ended: Long) {}
}
