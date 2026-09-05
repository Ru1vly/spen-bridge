package com.spenonlinux.app

import android.util.Log
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

class PenEventSender(
    private var host: String,
    private var port: Int,
    private val listener: StatusListener? = null
) {
    companion object {
        private const val TAG = "PenEventSender"
        private const val CONNECT_TIMEOUT_MS = 3000
    }

    enum class Status {
        DISCONNECTED,
        CONNECTING,
        CONNECTED,
        ERROR
    }

    interface StatusListener {
        fun onStatusChanged(status: Status, message: String)
    }

    private val isRunning = AtomicBoolean(false)
    private val queue = LinkedBlockingQueue<ByteArray>(2000)
    private var networkThread: Thread? = null
    private var socket: Socket? = null
    private var outputStream: OutputStream? = null
    private var seq: Short = 0

    fun updateEndpoint(newHost: String, newPort: Int) {
        if (host != newHost || port != newPort) {
            host = newHost
            port = newPort
            disconnectSocket()
        }
    }

    fun start() {
        if (isRunning.getAndSet(true)) return
        networkThread = Thread({ runNetworkLoop() }, "PenEventSenderThread").apply {
            priority = Thread.MAX_PRIORITY
            start()
        }
    }

    fun stop() {
        isRunning.set(false)
        disconnectSocket()
        networkThread?.interrupt()
        networkThread = null
    }

    fun enqueueEvents(events: List<Protocol.Event>) {
        if (!isRunning.get() || events.isEmpty()) return
        seq = ((seq + 1) and 0x7FFF).toShort()
        val packet = Protocol.packEvents(events, seq)
        // Discard oldest packets if queue is full to avoid lag buildup
        while (!queue.offer(packet)) {
            queue.poll()
        }
    }

    private fun disconnectSocket() {
        try {
            outputStream?.close()
            socket?.close()
        } catch (e: Exception) {
            Log.d(TAG, "Error closing socket: ${e.message}")
        } finally {
            outputStream = null
            socket = null
        }
    }

    private fun runNetworkLoop() {
        while (isRunning.get()) {
            listener?.onStatusChanged(Status.CONNECTING, "Connecting to $host:$port...")
            try {
                val s = Socket()
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
                socket = s
                outputStream = s.getOutputStream()

                // Send initial handshake
                val handshake = Protocol.packHandshake()
                outputStream?.write(handshake)
                outputStream?.flush()

                listener?.onStatusChanged(Status.CONNECTED, "Connected to $host:$port")
                Log.i(TAG, "Connected to $host:$port with TCP_NODELAY")

                // Main send loop
                while (isRunning.get() && s.isConnected && !s.isClosed) {
                    val packet = queue.poll(500, java.util.concurrent.TimeUnit.MILLISECONDS)
                    if (packet != null) {
                        outputStream?.write(packet)
                        // Batch multiple pending packets before flushing to minimize overhead
                        while (true) {
                            val next = queue.poll() ?: break
                            outputStream?.write(next)
                        }
                        outputStream?.flush()
                    }
                }
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                Log.w(TAG, "Connection error: ${e.message}")
                listener?.onStatusChanged(Status.ERROR, "Error: ${e.localizedMessage}")
            } finally {
                disconnectSocket()
                listener?.onStatusChanged(Status.DISCONNECTED, "Disconnected")
            }

            // Sleep before auto-reconnecting
            if (isRunning.get()) {
                try {
                    Thread.sleep(2000)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }
    }
}
