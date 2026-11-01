package com.spenbridge.app

import java.io.DataOutputStream

/** Fixed-size primitive timing records: never stores pen positions or credentials. */
internal class TimingTraceBuffer(private val capacity: Int) {
    init { require(capacity in 1..200000) }
    private val words = LongArray(capacity * 8)
    var seen = 0L
        private set
    var stored = 0
        private set
    private var closed = false

    @Synchronized fun append(kind: Long, session: Long, sequence: Long, count: Long,
                             t0: Long, t1: Long, t2: Long, checksum: Long) {
        if (closed) return
        seen++
        if (stored == capacity) return
        var i = stored++ * 8
        words[i++] = kind; words[i++] = session; words[i++] = sequence; words[i++] = count
        words[i++] = t0; words[i++] = t1; words[i++] = t2; words[i] = checksum
    }

    @Synchronized fun freeze() { closed = true }

    /** Only called after freeze, on the export worker. */
    fun writeTo(output: DataOutputStream) {
        check(closed)
        for (i in 0 until stored * 8) output.writeLong(words[i])
    }
}
