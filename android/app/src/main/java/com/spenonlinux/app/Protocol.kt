package com.spenonlinux.app

import java.nio.ByteBuffer
import java.nio.ByteOrder

object Protocol {
    val MAGIC = byteArrayOf('S'.code.toByte(), 'P'.code.toByte(), 'E'.code.toByte(), 'N'.code.toByte())
    const val HEADER_SIZE = 9
    const val EVENT_RECORD_SIZE = 24

    // Packet Types
    const val PKT_EVENT: Byte = 1
    const val PKT_PING: Byte = 2
    const val PKT_PONG: Byte = 3
    const val PKT_HANDSHAKE: Byte = 4

    // Action Types
    const val ACTION_HOVER_MOVE: Byte = 0
    const val ACTION_HOVER_ENTER: Byte = 1
    const val ACTION_HOVER_EXIT: Byte = 2
    const val ACTION_DOWN: Byte = 3
    const val ACTION_MOVE: Byte = 4
    const val ACTION_UP: Byte = 5
    const val ACTION_CANCEL: Byte = 6

    // Tool Types
    const val TOOL_STYLUS: Byte = 0
    const val TOOL_ERASER: Byte = 1
    const val TOOL_FINGER: Byte = 2

    // Button Flags
    const val BUTTON_STYLUS: Short = 1 shl 0
    const val BUTTON_STYLUS2: Short = 1 shl 1
    const val BUTTON_TOUCH: Short = 1 shl 2

    data class Event(
        val action: Byte,
        val toolType: Byte,
        val buttons: Short,
        val x: Float,
        val y: Float,
        val pressure: Float,
        val tiltX: Float = 0f,
        val tiltY: Float = 0f
    )

    fun packEvents(events: List<Event>, seq: Short = 0): ByteArray {
        val payloadLen = events.size * EVENT_RECORD_SIZE
        val buffer = ByteBuffer.allocate(HEADER_SIZE + payloadLen).order(ByteOrder.LITTLE_ENDIAN)

        // Header (9 bytes)
        buffer.put(MAGIC)
        buffer.put(PKT_EVENT)
        buffer.putShort(seq)
        buffer.putShort(payloadLen.toShort())

        // Records (24 bytes each)
        for (ev in events) {
            buffer.put(ev.action)
            buffer.put(ev.toolType)
            buffer.putShort(ev.buttons)
            buffer.putFloat(ev.x.coerceIn(0f, 1f))
            buffer.putFloat(ev.y.coerceIn(0f, 1f))
            buffer.putFloat(ev.pressure.coerceIn(0f, 1f))
            buffer.putFloat(ev.tiltX.coerceIn(-90f, 90f))
            buffer.putFloat(ev.tiltY.coerceIn(-90f, 90f))
        }

        return buffer.array()
    }

    fun packHandshake(seq: Short = 0): ByteArray {
        val buffer = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(MAGIC)
        buffer.put(PKT_HANDSHAKE)
        buffer.putShort(seq)
        buffer.putShort(0)
        return buffer.array()
    }

    fun packPing(seq: Short = 0): ByteArray {
        val buffer = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(MAGIC)
        buffer.put(PKT_PING)
        buffer.putShort(seq)
        buffer.putShort(0)
        return buffer.array()
    }
}
