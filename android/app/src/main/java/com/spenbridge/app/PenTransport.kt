package com.spenbridge.app

import java.io.IOException
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Platform-independent transport owner; only cancellation closes its raw socket. */
class PenTransport(
    endpoint: ConnectionEndpoint,
    private val observer: (Snapshot) -> Unit,
    private val openLink: (ConnectionEndpoint, (Socket) -> Boolean) -> ProtocolLink = SocketProtocolLink.Companion::open,
    private val buffer: SessionBuffer = SessionBuffer(),
    private val retryMillis: Long = 2000,
    private val heartbeatMillis: Long = 1000,
    private val stallMillis: Long = 6000
) {
    init { require(retryMillis > 0 && heartbeatMillis > 0 && stallMillis > 0) }
    enum class State { DISCONNECTED, CONNECTING, CONNECTED, ERROR, PAIRING_REQUIRED }
    data class Snapshot(val generation: Long, val state: State)
    // Java monitor waits are interrupted by stop and endpoint changes.
    @Suppress("PLATFORM_CLASS_MAPPED_TO_KOTLIN")
    private val lock = Object()
    private var endpoint = endpoint
    private var generation = 0L
    private var running = false
    private var worker: Thread? = null
    private var rawSocket: Socket? = null
    private var authenticated: Long? = null
    @Volatile private var lastProgress = System.nanoTime()
    @Volatile var snapshot = Snapshot(0, State.DISCONNECTED)
        private set

    fun endpoint(): ConnectionEndpoint = synchronized(lock) { endpoint }
    fun isCurrent(update: Snapshot): Boolean = synchronized(lock) { generation == update.generation && snapshot == update }

    fun updateEndpoint(replacement: ConnectionEndpoint) {
        val old = synchronized(lock) {
            if (endpoint == replacement) return
            endpoint = replacement
            generation++
            authenticated = null
            buffer.clear()
            rawSocket.also { rawSocket = null; lock.notifyAll() }
        }
        cancelSocket(old)
    }

    fun start() {
        synchronized(lock) {
            if (running) return
            check(worker?.isAlive != true) { "The previous connection worker is still stopping" }
            running = true
            worker = Thread(::run, "SPenTransport").apply { isDaemon = true; start() }
        }
    }

    fun stop() {
        val thread: Thread?
        val old: Socket?
        val stopped: Snapshot
        synchronized(lock) {
            running = false
            generation++
            authenticated = null
            buffer.clear()
            old = rawSocket
            rawSocket = null
            thread = worker
            stopped = Snapshot(generation, State.DISCONNECTED)
            snapshot = stopped
            lock.notifyAll()
        }
        cancelSocket(old) // Raw close interrupts blocked TLS reads/writes without TLS locks.
        thread?.interrupt()
        if (thread !== Thread.currentThread()) {
            thread?.join(1500)
            check(thread?.isAlive != true) { "Connection cleanup has not finished" }
        }
        observer(stopped)
    }

    /** UI acknowledges a new session only after clearing its active pointer. */
    fun resumeCapture(session: Long) {
        synchronized(lock) {
            if (running && generation == session && authenticated == session) buffer.begin(session)
        }
    }

    fun resetSession() {
        val old = synchronized(lock) {
            generation++
            authenticated = null
            buffer.clear()
            rawSocket.also { rawSocket = null; lock.notifyAll() }
        }
        cancelSocket(old)
    }

    fun enqueue(events: List<Protocol.Event>) {
        when (buffer.offer(events)) {
            SessionBuffer.Offer.RESET_REQUIRED -> resetSession()
            SessionBuffer.Offer.ACCEPTED -> synchronized(lock) { lock.notifyAll() }
            SessionBuffer.Offer.OFFLINE -> Unit
        }
    }

    private fun cancelSocket(socket: Socket?) {
        try { socket?.close() } catch (_: IOException) { }
    }

    private fun active(session: Long): Boolean = synchronized(lock) { running && generation == session }

    private fun publish(session: Long, state: State) {
        val update = synchronized(lock) {
            if (!running || generation != session) return
            Snapshot(session, state).also { snapshot = it }
        }
        observer(update)
    }

    private fun run() {
        val watchdog = Executors.newSingleThreadScheduledExecutor { work ->
            Thread(work, "SPenNetworkDeadline").apply { isDaemon = true }
        }
        watchdog.scheduleWithFixedDelay({
            val stale = synchronized(lock) {
                rawSocket.takeIf { running && System.nanoTime() - lastProgress > TimeUnit.MILLISECONDS.toNanos(stallMillis) }
            }
            try { stale?.close() } catch (_: IOException) { }
        }, minOf(500, stallMillis / 2).coerceAtLeast(1), minOf(500, stallMillis / 2).coerceAtLeast(1), TimeUnit.MILLISECONDS)
        try {
            while (true) {
                val target: ConnectionEndpoint
                val session: Long
                synchronized(lock) {
                    if (!running) return
                    target = endpoint
                    session = ++generation
                    buffer.clear()
                }
                if (!ConnectionEndpoint.validHost(target.host) || target.port !in 1..65535 || !target.isPaired()) {
                    publish(session, State.PAIRING_REQUIRED)
                    synchronized(lock) { if (active(session)) lock.wait(retryMillis) }
                    continue
                }
                publish(session, State.CONNECTING)
                var link: ProtocolLink? = null
                try {
                    lastProgress = System.nanoTime()
                    link = openLink(target) { socket ->
                        synchronized(lock) {
                            if (!active(session)) false else { rawSocket = socket; true }
                        }
                    }
                    if (!active(session)) {
                        continue
                    }
                    synchronized(lock) {
                        authenticated = session
                    }
                    lastProgress = System.nanoTime()
                    publish(session, State.CONNECTED)
                    var sequence: Short = 0
                    var heartbeat = System.nanoTime()
                    while (active(session)) {
                        if (System.nanoTime() >= heartbeat) {
                            link.send(Protocol.packPing(sequence))
                            val response = link.receive(2000)
                            if (response.kind != Protocol.PKT_PONG || response.sequence != sequence || response.payload.isNotEmpty()) {
                                throw IOException("Desktop heartbeat did not match")
                            }
                            sequence = (sequence + 1).toShort()
                            lastProgress = System.nanoTime()
                            heartbeat = lastProgress + TimeUnit.MILLISECONDS.toNanos(heartbeatMillis)
                        }
                        val batch = buffer.take(session)
                        if (batch != null) {
                            if (!active(session)) break
                            for (frame in Protocol.packEventBatches(batch.events, sequence)) {
                                link.send(frame)
                                sequence = (sequence + 1).toShort()
                            }
                            lastProgress = System.nanoTime()
                        } else synchronized(lock) {
                            if (active(session) && buffer.size() == 0) {
                                lock.wait(TimeUnit.NANOSECONDS.toMillis(heartbeat - System.nanoTime()).coerceIn(1, 100))
                            }
                        }
                    }
                } catch (_: InterruptedException) {
                    if (!active(session)) break
                } catch (_: Exception) {
                    publish(session, State.ERROR)
                } finally {
                    val old = synchronized(lock) {
                        if (generation == session) {
                            authenticated = null
                            buffer.clear()
                            rawSocket.also { rawSocket = null }
                        } else null
                    }
                    try { old?.close() } catch (_: IOException) { }
                    try { link?.close() } catch (_: Exception) { }
                }
                synchronized(lock) { if (active(session)) lock.wait(retryMillis) }
            }
        } catch (_: InterruptedException) {
            // Stop interrupts both retry waits and a pending DNS result wait.
        } finally {
            watchdog.shutdownNow()
            try { watchdog.awaitTermination(1, TimeUnit.SECONDS) } catch (_: InterruptedException) { }
            synchronized(lock) { if (worker === Thread.currentThread()) worker = null }
        }
    }
}
