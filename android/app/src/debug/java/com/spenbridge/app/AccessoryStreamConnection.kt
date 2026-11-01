package com.spenbridge.app

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.hardware.usb.UsbAccessory
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.ParcelFileDescriptor
import android.os.Process
import java.io.EOFException
import java.io.IOException
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Debug-only accessory experiment; no permission prompt or USB mode switch.
 * Caller must already own accessory permission. Open never runs on the UI thread.
 * Closing the published socket cancels opening and active I/O alike.
 */
@androidx.annotation.RequiresApi(30)
internal class AccessoryStreamConnection private constructor(
    context: Context,
    private val accessory: UsbAccessory?,
    private val fixture: ParcelFileDescriptor?,
    private val lifetimeSeconds: Int
) : AutoCloseable {
    private val context = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    private val pair = ParcelFileDescriptor.createSocketPair()
    private val helperStopped = CountDownLatch(1)
    private var bound = false // Accessed only on main looper.
    private var remote: Messenger? = null
    val socket = try { StreamSocket(DescriptorByteTransport(pair[0], ::requestStop)) }
        catch (error: Throwable) { closeExtraDescriptors(); throw error }
    var helperPid = -1
        private set

    private fun closeExtraDescriptors() {
        try { pair[1].close() } catch (_: IOException) { }
        try { fixture?.close() } catch (_: IOException) { }
    }
    private fun requestStop() {
        closed.set(true)
        main.post {
            try { remote?.send(Message.obtain(null, AccessoryRelayService.STOP)) } catch (_: Exception) { }
            if (bound) {
                bound = false
                try { context.unbindService(connection) } catch (_: IllegalArgumentException) { }
            }
            closeExtraDescriptors()
        }
    }
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            if (closed.get()) { requestStop(); return }
            try {
                service.linkToDeath({
                    helperStopped.countDown()
                    try { socket.close() } catch (_: IOException) { }
                }, 0)
                remote = Messenger(service)
                val data = Bundle().apply {
                    putParcelable("socket", pair[1])
                    accessory?.let { putParcelable("accessory", it) }
                    fixture?.let { putParcelable("fixture", it) }
                }
                remote!!.send(Message.obtain(null, AccessoryRelayService.START).apply {
                    arg1 = lifetimeSeconds
                    this.data = data
                })
            } catch (_: Exception) {
                try { socket.close() } catch (_: IOException) { }
            } finally { closeExtraDescriptors() }
        }
        override fun onServiceDisconnected(name: ComponentName) {
            helperStopped.countDown()
            try { socket.close() } catch (_: IOException) { }
        }
        override fun onNullBinding(name: ComponentName) {
            try { socket.close() } catch (_: IOException) { }
        }
        override fun onBindingDied(name: ComponentName) {
            helperStopped.countDown()
            try { socket.close() } catch (_: IOException) { }
        }
    }
    private fun bind() {
        main.post {
            if (!closed.get()) {
                try {
                    bound = context.bindService(Intent(context, AccessoryRelayService::class.java), connection, Context.BIND_AUTO_CREATE)
                    if (!bound) socket.close()
                } catch (_: Exception) { try { socket.close() } catch (_: IOException) { } }
            }
        }
    }
    override fun close() { socket.close() }
    internal fun awaitHelperStopped(timeoutMillis: Long): Boolean =
        helperStopped.await(timeoutMillis, TimeUnit.MILLISECONDS)

    companion object {
        fun open(context: Context, accessory: UsbAccessory, publish: (Socket) -> Boolean,
                 timeoutMillis: Int = 5000, lifetimeSeconds: Int = 15): AccessoryStreamConnection {
            val manager = context.getSystemService(UsbManager::class.java)
            require(manager.hasPermission(accessory)) { "Existing accessory permission required" }
            return connect(context, accessory, null, publish, timeoutMillis, lifetimeSeconds)
        }
        /** Socket-backed USB fixture; never opens a device or asks for permission. */
        internal fun openFixture(context: Context, descriptor: ParcelFileDescriptor,
                                 publish: (Socket) -> Boolean = { true }, timeoutMillis: Int = 5000,
                                 lifetimeSeconds: Int = 15): AccessoryStreamConnection =
            connect(context, null, descriptor, publish, timeoutMillis, lifetimeSeconds)

        private fun connect(context: Context, accessory: UsbAccessory?, fixture: ParcelFileDescriptor?,
                            publish: (Socket) -> Boolean, timeoutMillis: Int, lifetimeSeconds: Int): AccessoryStreamConnection {
            require(Build.VERSION.SDK_INT >= 30 && timeoutMillis in 1..10_000 && lifetimeSeconds in 1..15)
            check(Looper.myLooper() != Looper.getMainLooper()) { "Accessory open must not block the UI" }
            val session = AccessoryStreamConnection(context, accessory, fixture, lifetimeSeconds)
            val until = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis.toLong())
            try {
                if (!publish(session.socket)) throw InterruptedException("Accessory open cancelled")
                session.bind()
                val header = ByteArray(8)
                var offset = 0
                while (offset < header.size) {
                    val remaining = TimeUnit.NANOSECONDS.toMillis(until - System.nanoTime()).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
                    if (remaining <= 0) throw SocketTimeoutException("Accessory helper deadline expired")
                    session.socket.soTimeout = remaining
                    val count = session.socket.inputStream.read(header, offset, header.size-offset)
                    if (count < 0) throw EOFException("Accessory helper disconnected")
                    offset += count
                }
                val parsed = ByteBuffer.wrap(header)
                if (parsed.int != 0x53505541) throw IOException("Invalid accessory helper readiness")
                session.helperPid = parsed.int
                if (session.helperPid <= 0 || session.helperPid == Process.myPid()) throw IOException("Accessory helper isolation failed")
                session.socket.soTimeout = 0
                return session
            } catch (error: Throwable) {
                try { session.close() } catch (_: IOException) { }
                throw error
            }
        }
    }
}
