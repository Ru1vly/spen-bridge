package com.spenbridge.app

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
    // Holds un-serialized event batches, not packed bytes: packing
    // (Protocol.packEvents(), which allocates a ByteBuffer) happens on
    // PenEventSenderThread in runNetworkLoop() below, not on the calling
    // thread - enqueueEvents() is always called from the UI/input-dispatch
    // thread (PenSurfaceView.onTouchEvent/onHoverEvent), which also owns
    // onDraw(); doing allocation-heavy work there right before a frame has
    // to be drawn is exactly the kind of thing that shows up as dropped
    // frames / stroke jitter under GC pressure at high sampling rates.
    private val queue = LinkedBlockingQueue<List<Protocol.Event>>(2000)
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
        // events is already a fresh, fully-copied-out-of-MotionEvent list
        // (PenSurfaceView never reuses/mutates it afterward) - safe to hand
        // the reference straight to the network thread with no copy here.
        // Discard oldest batches if queue is full to avoid lag buildup.
        while (!queue.offer(events)) {
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

                // Main send loop. Serialization (Protocol.packEvents(), which
                // allocates a ByteBuffer) happens here on the network thread,
                // not at enqueue time on the UI thread - see enqueueEvents().
                while (isRunning.get() && s.isConnected && !s.isClosed) {
                    val first = queue.poll(500, java.util.concurrent.TimeUnit.MILLISECONDS) ?: continue

                    // Drain any already-queued backlog too (a GC pause,
                    // scheduler hiccup, or Wi-Fi stall can let several
                    // batches pile up) so the whole burst goes out as ONE
                    // write() call instead of one write()/TCP segment per
                    // batch - tcpNoDelay=true means Nagle isn't there to
                    // coalesce separate write()s for us.
                    var totalLen = 0
                    val packed = ArrayList<ByteArray>(4)
                    for (batch in sequenceOf(first) + generateSequence { queue.poll() }) {
                        seq = ((seq + 1) and 0x7FFF).toShort()
                        val p = Protocol.packEvents(batch, seq)
                        packed.add(p)
                        totalLen += p.size
                    }

                    val combined = if (packed.size == 1) {
                        packed[0]
                    } else {
                        val dst = ByteArray(totalLen)
                        var offset = 0
                        for (p in packed) {
                            System.arraycopy(p, 0, dst, offset, p.size)
                            offset += p.size
                        }
                        dst
                    }

                    outputStream?.write(combined)
                    outputStream?.flush()
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
