package com.spenbridge.app

import java.util.ArrayDeque

/** Bounded, session-scoped input. Overflow/staleness invalidates the session. */
class SessionBuffer(
    private val capacity: Int = 256,
    private val maxAgeNanos: Long = 100_000_000L,
    private val clock: () -> Long = System::nanoTime
) {
    enum class Offer { ACCEPTED, OFFLINE, RESET_REQUIRED }
    data class Batch(val session: Long, val events: List<Protocol.Event>, val created: Long)
    private val pending = ArrayDeque<Batch>()
    private var current: Long? = null
    private var records = 0

    init { require(capacity > 0 && maxAgeNanos > 0) }

    @Synchronized fun begin(session: Long) {
        clear()
        current = session
    }

    @Synchronized fun clear() {
        current = null
        pending.clear()
        records = 0
    }

    @Synchronized fun offer(events: List<Protocol.Event>): Offer {
        val session = current ?: return Offer.OFFLINE
        if (events.isEmpty()) return Offer.ACCEPTED
        if (events.any { !it.isValid() } || events.size > capacity - records) {
            clear()
            return Offer.RESET_REQUIRED
        }
        pending.addLast(Batch(session, events.toList(), clock()))
        records += events.size
        return Offer.ACCEPTED
    }

    @Synchronized fun take(session: Long): Batch? {
        if (current != session) return null
        val batch = pending.pollFirst() ?: return null
        records -= batch.events.size
        if (clock() - batch.created > maxAgeNanos) {
            clear()
            throw StaleInputException()
        }
        return batch
    }

    @Synchronized fun isActive(session: Long): Boolean = current == session
    @Synchronized fun size(): Int = records

    class StaleInputException : Exception("The input session stalled and was reset")
}
