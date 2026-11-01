package com.spenbridge.app

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log

/** Android lifecycle/radio adapter; PenTransport owns all network I/O. */
class PenEventSender(
    private val appContext: Context,
    host: String,
    port: Int,
    private val listener: StatusListener? = null,
    fingerprint: String = "",
    pairingCode: String = ""
) {
    companion object { private const val TAG = "PenEventSender" }
    enum class Status { DISCONNECTED, CONNECTING, CONNECTED, ERROR, COOLDOWN, PAIRING_REQUIRED }
    interface StatusListener { fun onStatusChanged(status: Status, message: String) }

    private val handler = Handler(Looper.getMainLooper())
    private val statusLock = Any()
    private var pending: PenTransport.Snapshot? = null
    private var notificationScheduled = false
    @Volatile private var foreground = false
    private var wifiLock: WifiManager.WifiLock? = null
    private val transport = PenTransport(ConnectionEndpoint(host, port, fingerprint, pairingCode), ::onTransportStatus)
    val currentStatus: Status get() = Status.valueOf(transport.snapshot.state.name)
    val currentGeneration: Long get() = transport.snapshot.generation

    private val notifyStatus = Runnable {
        val update = synchronized(statusLock) {
            notificationScheduled = false
            pending.also { pending = null }
        }
        if (update != null && transport.isCurrent(update)) {
            val status = Status.valueOf(update.state.name)
            if (foreground && status == Status.CONNECTED && update.mode == PenTransport.Mode.WIFI) acquireWifiLock()
            else releaseWifiLock()
            val endpoint = transport.endpoint()
            val connectionType = appContext.getString(
                if (update.mode == PenTransport.Mode.USB) R.string.connection_usb else R.string.connection_network)
            val message = when (status) {
                Status.DISCONNECTED -> appContext.getString(R.string.status_disconnected)
                Status.CONNECTING -> appContext.getString(R.string.status_connecting_transport, connectionType)
                Status.CONNECTED -> appContext.getString(R.string.status_connected_transport, connectionType)
                Status.COOLDOWN -> appContext.getString(if (ConnectionEndpoint.validHost(endpoint.host) && !endpoint.isLoopback())
                    R.string.status_both_failed else R.string.status_wifi_address_required)
                Status.PAIRING_REQUIRED -> appContext.getString(R.string.status_pairing_required)
                Status.ERROR -> appContext.getString(if (update.mode == PenTransport.Mode.USB) R.string.status_usb_error else R.string.status_connection_error)
            }
            listener?.onStatusChanged(status, message)
        }
    }

    private fun onTransportStatus(update: PenTransport.Snapshot) {
        val schedule = synchronized(statusLock) {
            pending = update
            if (notificationScheduled) false else { notificationScheduled = true; true }
        }
        if (schedule) handler.post(notifyStatus)
    }

    fun updateEndpoint(host: String, port: Int, fingerprint: String = "", pairingCode: String = "") {
        transport.updateEndpoint(ConnectionEndpoint(host, port, PairingProtocol.normalizeFingerprint(fingerprint), pairingCode.trim()))
    }

    fun start() {
        foreground = true
        try { transport.start() } catch (_: IllegalStateException) {
            listener?.onStatusChanged(Status.ERROR, appContext.getString(R.string.status_cleanup_pending))
        }
    }

    fun resumeCapture(generation: Long) { transport.resumeCapture(generation) }
    fun resetSession() { transport.resetSession() }
    fun enqueueEvents(events: List<Protocol.Event>) { transport.enqueue(events) }

    fun stop() {
        foreground = false
        try { transport.stop() } catch (_: IllegalStateException) {
            Log.w(TAG, "Connection worker cleanup is still pending")
        } finally {
            handler.removeCallbacks(notifyStatus)
            synchronized(statusLock) { pending = null; notificationScheduled = false }
            releaseWifiLock()
        }
    }

    private fun acquireWifiLock() {
        if (wifiLock != null) return
        try {
            val manager = appContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
            val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) WifiManager.WIFI_MODE_FULL_LOW_LATENCY
                       else @Suppress("DEPRECATION") WifiManager.WIFI_MODE_FULL_HIGH_PERF
            wifiLock = manager.createWifiLock(mode, "$TAG:PenStream").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (_: Exception) {
            Log.w(TAG, "Wi-Fi latency lock unavailable; continuing with normal radio management")
        }
    }

    private fun releaseWifiLock() {
        try { wifiLock?.let { if (it.isHeld) it.release() } }
        catch (_: Exception) { Log.w(TAG, "Wi-Fi latency lock release failed") }
        finally { wifiLock = null }
    }
}
