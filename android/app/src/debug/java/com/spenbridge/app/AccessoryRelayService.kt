package com.spenbridge.app

import android.app.Application
import android.app.Service
import android.content.Intent
import android.hardware.usb.UsbAccessory
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.ParcelFileDescriptor
import android.os.Process
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.ByteBuffer

/** Debug-only, non-exported helper. Blocking accessory I/O lives only here.
 * Stopping kills this dedicated process, never the normal pen application.
 */
class AccessoryRelayService : Service() {
    private val main = Handler(Looper.getMainLooper())
    private var started = false
    private val messenger = Messenger(Handler(Looper.getMainLooper()) { message ->
        if (message.sendingUid == Process.myUid()) {
            when (message.what) {
                START -> startRelay(message)
                STOP -> terminateHelper()
            }
        }
        true
    })

    override fun onCreate() {
        super.onCreate()
        check(Build.VERSION.SDK_INT >= 28 && Application.getProcessName() == "$packageName:accessory_relay") {
            "Accessory relay must run in its dedicated process"
        }
        // Also covers a client that binds and never sends START.
        main.postDelayed({ terminateHelper() }, 20_000)
    }
    override fun onBind(intent: Intent): IBinder = messenger.binder
    override fun onUnbind(intent: Intent): Boolean {
        terminateHelper()
        return false
    }
    override fun onDestroy() {
        terminateHelper()
        super.onDestroy()
    }
    private fun terminateHelper() {
        // Independent guard at the sole process-termination site.
        if (Build.VERSION.SDK_INT >= 28 && Application.getProcessName() == "$packageName:accessory_relay") {
            Process.killProcess(Process.myPid())
        }
    }
    @Suppress("DEPRECATION")
    private fun startRelay(message: Message) {
        if (started) return // Never replace an existing I/O owner.
        started = true
        val data = message.data.apply { classLoader = ParcelFileDescriptor::class.java.classLoader }
        val socket = data.getParcelable<ParcelFileDescriptor>("socket")
        val fixture = data.getParcelable<ParcelFileDescriptor>("fixture")
        val accessory = data.getParcelable<UsbAccessory>("accessory")
        val seconds = message.arg1
        if (socket == null || seconds !in 1..15 || (fixture == null) == (accessory == null)) {
            socket?.close(); fixture?.close(); terminateHelper(); return
        }
        main.postDelayed({ terminateHelper() }, seconds * 1000L)
        Thread({
            try {
                val device = fixture ?: run {
                    val manager = getSystemService(UsbManager::class.java)
                    check(manager.hasPermission(requireNotNull(accessory))) { "Accessory permission required" }
                    requireNotNull(manager.openAccessory(accessory)) { "Cannot open accessory" }
                }
                val usbInput = FileInputStream(device.fileDescriptor)
                val usbOutput = FileOutputStream(device.fileDescriptor)
                val appInput = FileInputStream(socket.fileDescriptor)
                val appOutput = FileOutputStream(socket.fileDescriptor)
                // Local IPC readiness header, consumed before any TLS bytes.
                appOutput.write(ByteBuffer.allocate(8).putInt(0x53505541).putInt(Process.myPid()).array())
                Thread({
                    try {
                        val bytes = ByteArray(16_384)
                        while (true) {
                            val count = usbInput.read(bytes)
                            if (count < 0) break
                            if (count > 0) appOutput.write(bytes, 0, count)
                        }
                    } catch (_: Exception) { }
                    finally { main.post { terminateHelper() } }
                }, "SPenAccessoryRead").start()
                val bytes = ByteArray(16_384)
                while (true) {
                    val count = appInput.read(bytes)
                    if (count < 0) break
                    if (count > 0) usbOutput.write(bytes, 0, count)
                }
            } catch (_: Exception) { }
            finally { main.post { terminateHelper() } }
            // FDs are owned by this one-shot process. Kernel closes them on
            // termination; never wait on a blocked accessory stream to close.
        }, "SPenAccessoryWrite").start()
    }
    companion object {
        internal const val START = 1
        internal const val STOP = 2
    }
}
