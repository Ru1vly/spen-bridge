package com.spenbridge.app

import java.nio.ByteBuffer
import java.nio.ByteOrder

object Protocol {
    val MAGIC = byteArrayOf('S'.code.toByte(), 'P'.code.toByte(), 'E'.code.toByte(), 'N'.code.toByte())
    const val HEADER_SIZE = 9
    const val EVENT_RECORD_SIZE = 24
    const val MAX_EVENTS_PER_PACKET = 65535 / EVENT_RECORD_SIZE
    const val PKT_EVENT: Byte = 1
    const val PKT_PING: Byte = 2
    const val PKT_PONG: Byte = 3
    const val PKT_HANDSHAKE: Byte = 4
    const val ACTION_HOVER_MOVE: Byte = 0
    const val ACTION_HOVER_ENTER: Byte = 1
    const val ACTION_HOVER_EXIT: Byte = 2
    const val ACTION_DOWN: Byte = 3
    const val ACTION_MOVE: Byte = 4
    const val ACTION_UP: Byte = 5
    const val ACTION_CANCEL: Byte = 6
    const val TOOL_STYLUS: Byte = 0
    const val TOOL_ERASER: Byte = 1
    const val TOOL_FINGER: Byte = 2
    const val BUTTON_STYLUS: Short = 1
    const val BUTTON_STYLUS2: Short = 2
    const val BUTTON_TOUCH: Short = 4

    data class Event(
        val action: Byte, val toolType: Byte, val buttons: Short,
        val x: Float, val y: Float, val pressure: Float,
        val tiltX: Float = 0f, val tiltY: Float = 0f
    ) {
        fun isValid(): Boolean = action.toInt() in 0..6 && toolType.toInt() in 0..2 &&
            buttons.toInt() in 0..7 && x.isFinite() && y.isFinite() && pressure.isFinite() &&
            tiltX.isFinite() && tiltY.isFinite() && x in 0f..1f && y in 0f..1f &&
            pressure in 0f..1f && tiltX in -90f..90f && tiltY in -90f..90f
    }

    data class Packet(val kind: Byte, val sequence: Short, val payload: ByteArray)

    fun packPacket(kind: Byte, sequence: Short, payload: ByteArray = byteArrayOf()): ByteArray {
        require(kind in PKT_EVENT..PKT_HANDSHAKE && payload.size <= 65535) { "Invalid packet" }
        return ByteBuffer.allocate(HEADER_SIZE + payload.size).order(ByteOrder.LITTLE_ENDIAN).apply {
            put(MAGIC)
            put(kind)
            putShort(sequence)
            putShort(payload.size.toShort())
            put(payload)
        }.array()
    }

    /** Single-writer reusable frame storage; bytes remain owned until send returns. */
    class EventEncoder {
        var bytes = ByteArray(HEADER_SIZE + 16 * EVENT_RECORD_SIZE)
            private set
        private var frame = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)

        fun encode(events: List<Event>, offset: Int, count: Int, sequence: Short): Int {
            require(count in 1..MAX_EVENTS_PER_PACKET && offset >= 0 && offset <= events.size - count) {
                "Event batch exceeds protocol bounds"
            }
            val size = HEADER_SIZE + count * EVENT_RECORD_SIZE
            if (bytes.size < size) {
                bytes = ByteArray(minOf(HEADER_SIZE + MAX_EVENTS_PER_PACKET * EVENT_RECORD_SIZE,
                    maxOf(size, bytes.size * 2)))
                frame = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            }
            frame.clear()
            frame.put(MAGIC).put(PKT_EVENT).putShort(sequence).putShort((size - HEADER_SIZE).toShort())
            for (index in offset until offset + count) {
                val event = events[index]
                require(event.isValid()) { "Invalid pen event" }
                frame.put(event.action).put(event.toolType).putShort(event.buttons)
                frame.putFloat(event.x).putFloat(event.y).putFloat(event.pressure)
                frame.putFloat(event.tiltX).putFloat(event.tiltY)
            }
            return size
        }
    }

    fun packEvents(events: List<Event>, seq: Short = 0): ByteArray {
        val encoder = EventEncoder()
        val size = encoder.encode(events, 0, events.size, seq)
        return encoder.bytes.copyOf(size)
    }

    fun packEventBatches(events: List<Event>, firstSequence: Short): List<ByteArray> {
        if (events.isEmpty()) return emptyList()
        if (events.size <= MAX_EVENTS_PER_PACKET) return listOf(packEvents(events, firstSequence))
        var sequence = firstSequence
        return events.chunked(MAX_EVENTS_PER_PACKET).map { batch ->
            packEvents(batch, sequence).also { sequence = (sequence + 1).toShort() }
        }
    }

    fun packHandshake(seq: Short = 0, proof: ByteArray = byteArrayOf()): ByteArray =
        packPacket(PKT_HANDSHAKE, seq, proof)

    fun packPing(seq: Short = 0): ByteArray = packPacket(PKT_PING, seq)
}
