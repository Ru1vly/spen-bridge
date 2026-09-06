package com.spenonlinux.app

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

class PenEventSender(
    private val appContext: Context,
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
    private var wifiLock: WifiManager.WifiLock? = null

    fun updateEndpoint(newHost: String, newPort: Int) {
        if (host != newHost || port != newPort) {
            host = newHost
            port = newPort
            disconnectSocket()
        }
    }

    fun start() {
        if (isRunning.getAndSet(true)) return
        acquireWifiLock()
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
        releaseWifiLock()
    }

    /**
     * Without this, Android's Wi-Fi power management lets the radio drop into a
     * low-power polling state between packet bursts - normal for background
     * traffic, but it adds tens of milliseconds of latency to every burst of
     * pen events on a stream that's sending small packets continuously.
     * WIFI_MODE_FULL_LOW_LATENCY (falling back to WIFI_MODE_FULL_HIGH_PERF pre-Q)
     * keeps the radio active for the lifetime of the connection instead.
     */
    private fun acquireWifiLock() {
        if (wifiLock != null) return
        try {
            val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
            val lockMode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY
            } else {
                @Suppress("DEPRECATION")
                WifiManager.WIFI_MODE_FULL_HIGH_PERF
            }
            wifiLock = wifiManager.createWifiLock(lockMode, "$TAG:PenStream").apply {
                setReferenceCounted(false)
                acquire()
            }
            Log.i(TAG, "Wi-Fi low-latency lock acquired (mode=$lockMode)")
        } catch (e: Exception) {
            Log.w(TAG, "Could not acquire Wi-Fi lock: ${e.message}")
        }
    }

    private fun releaseWifiLock() {
        try {
            wifiLock?.let { if (it.isHeld) it.release() }
        } catch (e: Exception) {
            Log.d(TAG, "Error releasing Wi-Fi lock: ${e.message}")
        } finally {
            wifiLock = null
        }
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
