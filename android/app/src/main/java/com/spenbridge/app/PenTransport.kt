package com.spenbridge.app

import java.io.IOException
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ExecutorService
import java.util.concurrent.Future
import java.util.concurrent.FutureTask
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Platform-independent transport owner; only cancellation closes its raw socket. */
class PenTransport(
    endpoint: ConnectionEndpoint,
    private val observer: (Snapshot) -> Unit,
    private val openLink: (ConnectionEndpoint, (Socket) -> Boolean) -> ProtocolLink = SocketProtocolLink.Companion::open,
    private val buffer: SessionBuffer = SessionBuffer(),
    private val retryMillis: Long = 5000,
    private val heartbeatMillis: Long = 1000,
    private val stallMillis: Long = 6000,
    private val usbProbeMillis: Long = 2000,
    private val idleMillis: Long = 750,
    private val probeUsb: (ConnectionEndpoint, (Socket) -> Boolean) -> Boolean = SocketProtocolLink.Companion::probe
) {
    init { require(retryMillis > 0 && heartbeatMillis > 0 && stallMillis > 0 && usbProbeMillis > 0 && idleMillis > 0) }
    enum class State { DISCONNECTED, CONNECTING, CONNECTED, ERROR, COOLDOWN, PAIRING_REQUIRED }
    enum class Mode { USB, WIFI }
    data class Snapshot(val generation: Long, val state: State, val mode: Mode? = null)
    // Java monitor waits are interrupted by stop and endpoint changes.
    @Suppress("PLATFORM_CLASS_MAPPED_TO_KOTLIN")
    private val lock = Object()
    private var endpoint = endpoint
    private var generation = 0L
    private var running = false
    private var worker: Thread? = null
    private var rawSocket: Socket? = null
    private var probeSocket: Socket? = null
    private var usbReadySession: Long? = null
    private var usbReadyUntil = 0L
    private var lastInputNanos = System.nanoTime()
    private var contactHeld = false
    private var buttonHeld = false
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
            val sockets = rawSocket to probeSocket
            rawSocket = null
            probeSocket = null
            usbReadySession = null
            lock.notifyAll()
            sockets
        }
        cancelSocket(old.first)
        cancelSocket(old.second)
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
        val oldProbe: Socket?
        val stopped: Snapshot
        synchronized(lock) {
            running = false
            generation++
            authenticated = null
            buffer.clear()
            old = rawSocket
            oldProbe = probeSocket
            rawSocket = null
            probeSocket = null
            usbReadySession = null
            thread = worker
            stopped = Snapshot(generation, State.DISCONNECTED)
            snapshot = stopped
            lock.notifyAll()
        }
        cancelSocket(oldProbe)
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
            if (running && generation == session && authenticated == session && !buffer.isActive(session)) {
                buffer.begin(session)
                contactHeld = false
                buttonHeld = false
                lastInputNanos = System.nanoTime()
            }
        }
    }

    fun resetSession() {
        val old = synchronized(lock) {
            generation++
            authenticated = null
            buffer.clear()
            val sockets = rawSocket to probeSocket
            rawSocket = null
            probeSocket = null
            usbReadySession = null
            lock.notifyAll()
            sockets
        }
        cancelSocket(old.first)
        cancelSocket(old.second)
    }

    fun enqueue(events: List<Protocol.Event>) {
        val result = synchronized(lock) {
            buffer.offer(events).also { result ->
                if (result == SessionBuffer.Offer.ACCEPTED && events.isNotEmpty()) {
                    lastInputNanos = System.nanoTime()
                    InputTrace.queued(generation, events.size)
                    for (event in events) {
                        val neutral = event.action == Protocol.ACTION_CANCEL || event.action == Protocol.ACTION_HOVER_EXIT
                        contactHeld = !neutral && (event.action == Protocol.ACTION_DOWN || event.action == Protocol.ACTION_MOVE ||
                            (event.buttons.toInt() and Protocol.BUTTON_TOUCH.toInt()) != 0)
                        buttonHeld = !neutral && (event.buttons.toInt() and 3) != 0
                    }
                    lock.notifyAll()
                }
            }
        }
        if (result == SessionBuffer.Offer.RESET_REQUIRED) {
            InputTrace.queueReset(snapshot.generation, events.size, 1)
            resetSession()
        }
    }

    private fun idleForHandover(session: Long): Boolean =
        authenticated == session && buffer.isActive(session) && buffer.size() == 0 &&
        !contactHeld && !buttonHeld &&
        System.nanoTime() - lastInputNanos >= TimeUnit.MILLISECONDS.toNanos(idleMillis)

    private fun checkUsbUpgrade() {
        val candidate = synchronized(lock) {
            val state = snapshot
            if (running && state.state == State.CONNECTED && state.mode == Mode.WIFI && idleForHandover(generation)) {
                generation to endpoint.copy(host = "127.0.0.1")
            } else null
        } ?: return
        val (session, target) = candidate
        var ready = false
        try {
            ready = probeUsb(target) { socket ->
                synchronized(lock) {
                    if (!active(session)) false else { probeSocket = socket; true }
                }
            }
        } catch (_: Exception) {
            // An absent cable never interrupts a healthy Wi-Fi stream.
        } finally {
            val old = synchronized(lock) { probeSocket.also { probeSocket = null } }
            cancelSocket(old)
        }
        synchronized(lock) {
            if (ready && active(session) && snapshot.mode == Mode.WIFI) {
                usbReadySession = session
                usbReadyUntil = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(usbProbeMillis)
                lock.notifyAll()
            }
        }
    }

    private fun cancelSocket(socket: Socket?) {
        try { socket?.close() } catch (_: IOException) { }
    }

    private fun active(session: Long): Boolean = synchronized(lock) { running && generation == session }

    private fun publish(session: Long, state: State, mode: Mode? = null) {
        val update = synchronized(lock) {
            if (!running || generation != session) return
            Snapshot(session, state, mode).also { snapshot = it }
        }
        InputTrace.state(session, state.ordinal)
        observer(update)
    }

    private fun waitForRetry(session: Long) {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(retryMillis)
        synchronized(lock) {
            while (active(session)) {
                val remaining = deadline - System.nanoTime()
                if (remaining <= 0) return
                TimeUnit.NANOSECONDS.timedWait(lock, remaining)
            }
        }
    }

    private fun stopExecutors(vararg executors: ExecutorService) {
        executors.forEach { it.shutdownNow() }
        var interrupted = Thread.interrupted()
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1)
        for (executor in executors) {
            while (!executor.isTerminated) {
                val remaining = deadline - System.nanoTime()
                if (remaining <= 0) break
                try { executor.awaitTermination(remaining, TimeUnit.NANOSECONDS) }
                catch (_: InterruptedException) { interrupted = true }
            }
        }
        if (interrupted) Thread.currentThread().interrupt()
    }

    private fun run() {
        // A bounded reader is independent of the single ordered writer. A delayed
        // PONG must never prevent an available pen sample from being sent.
        val receiver = ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
            ArrayBlockingQueue<Runnable>(1), { work ->
                Thread(work, "SPenControlReceiver").apply { isDaemon = true }
            }, ThreadPoolExecutor.AbortPolicy())
        val watchdog = Executors.newScheduledThreadPool(2) { work ->
            Thread(work, "SPenNetworkDeadline").apply { isDaemon = true }
        }
        watchdog.scheduleWithFixedDelay({
            val stale = synchronized(lock) {
                rawSocket.takeIf { running && System.nanoTime() - lastProgress > TimeUnit.MILLISECONDS.toNanos(stallMillis) }
            }
            try { stale?.close() } catch (_: IOException) { }
        }, minOf(500, stallMillis / 2).coerceAtLeast(1), minOf(500, stallMillis / 2).coerceAtLeast(1), TimeUnit.MILLISECONDS)
        watchdog.scheduleWithFixedDelay(::checkUsbUpgrade, usbProbeMillis, usbProbeMillis, TimeUnit.MILLISECONDS)
        val encoder = Protocol.EventEncoder()
        var nextMode = Mode.USB
        var cycleEndpoint: ConnectionEndpoint? = null
        try {
            while (true) {
                val attempt = synchronized(lock) {
                    if (!running) null else {
                        val configured = endpoint
                        if (cycleEndpoint != configured) {
                            nextMode = Mode.USB
                            cycleEndpoint = configured
                        }
                        buffer.clear()
                        usbReadySession = null
                        Triple(configured, nextMode, ++generation)
                    }
                } ?: break
                val (configured, mode, session) = attempt
                val target = if (mode == Mode.USB) configured.copy(host = "127.0.0.1") else configured
                if (configured.port !in 1..65535 || !configured.isPaired()) {
                    publish(session, State.PAIRING_REQUIRED)
                    waitForRetry(session)
                    continue
                }
                publish(session, State.CONNECTING, mode)
                var connected = false
                var link: ProtocolLink? = null
                var response: Future<Protocol.Packet>? = null
                try {
                    if (!ConnectionEndpoint.validHost(target.host) || (mode == Mode.WIFI && target.isLoopback())) {
                        throw IOException("Configure the desktop Wi-Fi address in Settings")
                    }
                    lastProgress = System.nanoTime()
                    link = openLink(target) { socket ->
                        synchronized(lock) {
                            if (!active(session)) false else { rawSocket = socket; true }
                        }
                    }
                    if (!active(session)) {
                        nextMode = Mode.USB
                        cycleEndpoint = null
                        continue
                    }
                    synchronized(lock) {
                        authenticated = session
                    }
                    lastProgress = System.nanoTime()
                    connected = true
                    publish(session, State.CONNECTED, mode)
                    var sequence: Short = 0
                    var heartbeat = System.nanoTime()
                    var responseDeadline = 0L
                    var expectedPong: Short = 0
                    var pingBegan = 0L
                    var pingWritten = 0L
                    var pongReceived = 0L
                    val sessionLink = checkNotNull(link)
                    while (active(session)) {
                        val upgrade = synchronized(lock) {
                            if (mode == Mode.WIFI && usbReadySession == session &&
                                System.nanoTime() < usbReadyUntil && idleForHandover(session)) {
                                // Freeze capture atomically with the idle check. The new
                                // USB session requires a fresh UI acknowledgement.
                                authenticated = null
                                buffer.clear()
                                true
                            } else false
                        }
                        if (upgrade) break
                        val pending = response
                        if (pending != null) {
                            if (pending.isDone) {
                                val reply = pending.get()
                                if (reply.kind != Protocol.PKT_PONG || reply.sequence != expectedPong || reply.payload.isNotEmpty()) {
                                    throw IOException("Desktop heartbeat did not match")
                                }
                                if (pingBegan != 0L) InputTrace.heartbeat(session, expectedPong, pingBegan, pingWritten, pongReceived)
                                response = null
                                lastProgress = System.nanoTime()
                                heartbeat = lastProgress + TimeUnit.MILLISECONDS.toNanos(heartbeatMillis)
                            } else if (System.nanoTime() >= responseDeadline) {
                                throw IOException("Desktop heartbeat timed out")
                            }
                        }
                        if (response == null && System.nanoTime() >= heartbeat) {
                            expectedPong = sequence
                            pingBegan = if (InputTrace.enabled) System.nanoTime() else 0L
                            sessionLink.send(Protocol.packPing(sequence))
                            pingWritten = if (pingBegan != 0L) System.nanoTime() else 0L
                            sequence = (sequence + 1).toShort()
                            responseDeadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2)
                            val task = object : FutureTask<Protocol.Packet>({
                                sessionLink.receive(2000).also { pongReceived = if (pingBegan != 0L) System.nanoTime() else 0L }
                            }) {
                                override fun done() { synchronized(lock) { lock.notifyAll() } }
                            }
                            response = task
                            receiver.execute(task)
                        }
                        val batch = buffer.take(session)
                        if (batch != null) {
                            if (!active(session)) break
                            var offset = 0
                            while (offset < batch.events.size) {
                                val count = minOf(Protocol.MAX_EVENTS_PER_PACKET, batch.events.size - offset)
                                val size = encoder.encode(batch.events, offset, count, sequence)
                                val tracing = InputTrace.enabled
                                val began = if (tracing) System.nanoTime() else 0L
                                sessionLink.send(encoder.bytes, size)
                                if (tracing) InputTrace.packet(session, sequence, count, encoder.bytes, size,
                                    batch.created, began, System.nanoTime())
                                sequence = (sequence + 1).toShort()
                                offset += count
                            }
                            lastProgress = System.nanoTime()
                        } else synchronized(lock) {
                            if (active(session) && buffer.size() == 0) {
                                val deadline = if (response != null) responseDeadline else heartbeat
                                lock.wait(TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime()).coerceIn(1, 100))
                            }
                        }
                    }
                } catch (_: InterruptedException) {
                    // Cancellation is handled after releasing this attempt in finally.
                } catch (error: Exception) {
                    if (error is SessionBuffer.StaleInputException) InputTrace.queueReset(session, -1, 2)
                    publish(session, State.ERROR, mode)
                } finally {
                    val old = synchronized(lock) {
                        if (generation == session) {
                            authenticated = null
                            buffer.clear()
                            rawSocket.also { rawSocket = null }
                        } else null
                    }
                    // Close the raw socket before TLS cleanup to interrupt both
                    // a blocked writer and a pending control read without TLS locks.
                    try { old?.close() } catch (_: IOException) { }
                    response?.cancel(true)
                    (response as? Runnable)?.let { receiver.remove(it) }
                    try { link?.close() } catch (_: Exception) { }
                }
                if (!active(session)) {
                    nextMode = Mode.USB
                    cycleEndpoint = null
                    continue
                }
                if (mode == Mode.USB) {
                    // USB failed/lost its session: try Wi-Fi immediately, without cooldown.
                    nextMode = Mode.WIFI
                } else if (connected) {
                    // A previously working Wi-Fi session ended: start again with USB.
                    nextMode = Mode.USB
                } else {
                    // Neither route worked. One cooldown applies to the entire pair.
                    publish(session, State.COOLDOWN)
                    waitForRetry(session)
                    nextMode = Mode.USB
                }
            }
        } catch (_: InterruptedException) {
            // Stop interrupts both retry waits and a pending DNS result wait.
        } finally {
            val pendingProbe = synchronized(lock) { probeSocket.also { probeSocket = null } }
            cancelSocket(pendingProbe)
            stopExecutors(watchdog, receiver)
            synchronized(lock) { if (worker === Thread.currentThread()) worker = null }
        }
    }
}
