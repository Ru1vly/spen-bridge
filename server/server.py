"""Bounded TLS protocol-v2 server with exclusive authenticated input ownership."""
import asyncio
import hmac
import logging
import secrets
import socket
import sys
import time

from server.protocol import (
    HEADER_SIZE, EVENT_RECORD_SIZE, PKT_EVENT, PKT_PING, PKT_PONG, PKT_HANDSHAKE,
    unpack_header, unpack_events, pack_packet,
)
from server.security import AUTH_VERSION, NONCE_SIZE, auth_proof
from server.input_trace import get_controller

logger = logging.getLogger("SPenServer")


class _Budget:
    def __init__(self, rate):
        self.rate = rate
        self.tokens = rate * 2
        self.updated = time.monotonic()

    def consume(self, amount):
        now = time.monotonic()
        self.tokens = min(self.rate * 2, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if amount > self.tokens:
            raise ValueError("Connection traffic limit exceeded")
        self.tokens -= amount


class SPenServer:
    def __init__(self, tablet, host="127.0.0.1", port=40118,
                 on_client_connected=None, on_client_disconnected=None, on_stats=None,
                 on_device_error=None,
                 *, tls_context=None, pairing_code=None, max_connections=4,
                 handshake_timeout=5.0, idle_timeout=10.0, shutdown_timeout=2.0,
                 event_rate=10000, byte_rate=1024 * 1024, packet_rate=4000,
                 ):
        self.tablet, self.host, self.port = tablet, host, port
        self.input_trace = get_controller()
        if self.input_trace is not None:
            self.input_trace.backend_name = type(tablet).__name__
        self.on_client_connected = on_client_connected
        self.on_client_disconnected = on_client_disconnected
        self.on_stats = on_stats
        self.on_device_error = on_device_error
        self._device_failed = False
        self.tls_context, self.pairing_code = tls_context, pairing_code
        self.max_connections = max_connections
        self.handshake_timeout, self.idle_timeout = handshake_timeout, idle_timeout
        self.shutdown_timeout = shutdown_timeout
        self.event_rate, self.byte_rate, self.packet_rate = event_rate, byte_rate, packet_rate
        self.server = None
        self._running = False
        self.active_clients = set()
        self._writers = set()
        self._handlers = set()
        self._connections = set()
        self._accept_task = None
        self._owner = None
        self._stop_lock = asyncio.Lock()
        self.stats_events_count = self.stats_packets_count = self.total_events_count = 0
        self._last_stats_time = time.monotonic()

    @property
    def is_running(self):
        return self._running and self.server is not None

    @staticmethod
    def _callback(callback, *args):
        if callback:
            try:
                callback(*args)
            except Exception:
                logger.debug("Server callback failed", exc_info=True)

    async def _read_packet(self, reader, timeout, budget):
        async def read():
            header = await reader.readexactly(HEADER_SIZE)
            parsed = unpack_header(header)
            if parsed is None:
                raise ValueError("Invalid packet magic")
            kind, seq, size = parsed
            if kind == PKT_EVENT:
                if not size or size % EVENT_RECORD_SIZE:
                    raise ValueError("Incomplete event payload")
            elif kind == PKT_HANDSHAKE:
                if size != len(AUTH_VERSION) + NONCE_SIZE:
                    raise ValueError("Invalid authentication payload")
            elif kind == PKT_PING:
                if size:
                    raise ValueError("Ping must be empty")
            else:
                raise ValueError("Unexpected packet type")
            budget.consume(HEADER_SIZE + size)
            return kind, seq, await reader.readexactly(size)
        # A deadline covers the complete frame, so drip-fed bytes cannot keep
        # a held pen alive indefinitely.
        return await asyncio.wait_for(read(), timeout)

    async def _write_packet(self, writer, kind, seq, payload=b""):
        writer.write(pack_packet(kind, seq, payload))
        await asyncio.wait_for(writer.drain(), self.handshake_timeout)

    async def _handle_client(self, reader, writer):
        task = asyncio.current_task()
        if not self._running or len(self._writers) >= self.max_connections:
            writer.close()
            return
        self._writers.add(writer)
        self._handlers.add(task)
        peer = writer.get_extra_info("peername")
        address = f"{peer[0]}:{peer[1]}" if peer else "Unknown"
        owned = False
        bytes_budget, events_budget, packets_budget = (_Budget(self.byte_rate),
                                                      _Budget(self.event_rate),
                                                      _Budget(self.packet_rate))
        try:
            if writer.get_extra_info("ssl_object") is None or self.pairing_code is None:
                raise ValueError("TLS and pairing are required")
            sock = writer.get_extra_info("socket")
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            nonce = secrets.token_bytes(NONCE_SIZE)
            await self._write_packet(writer, PKT_HANDSHAKE, 0, AUTH_VERSION + nonce)
            kind, seq, proof = await self._read_packet(reader, self.handshake_timeout, bytes_budget)
            if (kind != PKT_HANDSHAKE or seq not in (0, 1)
                    or not hmac.compare_digest(proof, auth_proof(self.pairing_code, nonce, "client"))):
                raise ValueError("Pairing authentication failed")
            if seq == 1:
                # Authenticated, read-only readiness probe: never claim input,
                # reset the owner, or accept subsequent event packets.
                await self._write_packet(writer, PKT_HANDSHAKE, 1,
                                         auth_proof(self.pairing_code, nonce, "server"))
                return
            if not self._running or self._owner is not None:
                raise ValueError("Another paired client owns the tablet")
            # No await between checking and claiming ownership.
            self._owner = writer
            owned = True
            await self._write_packet(writer, PKT_HANDSHAKE, seq, auth_proof(self.pairing_code, nonce, "server"))
            self.active_clients.add(address)
            self._callback(self.on_client_connected, address)
            trace_session = time.perf_counter_ns()
            while self._running:
                kind, seq, payload = await self._read_packet(reader, self.idle_timeout, bytes_budget)
                packets_budget.consume(1)
                if kind == PKT_EVENT:
                    trace = self.input_trace
                    received = time.perf_counter_ns() if trace is not None and trace.enabled else 0
                    events = unpack_events(payload)
                    events_budget.consume(len(events))
                    self.stats_packets_count += 1
                    decoded = time.perf_counter_ns() if received else 0
                    success = False
                    try:
                        self._dispatch_event_groups([events])
                        success = True
                    except Exception as error:
                        self._fail_device(error)
                        raise
                    finally:
                        if received:
                            trace.packet(trace_session, seq, len(events), received, decoded,
                                         time.perf_counter_ns(), payload, success=success)
                elif kind == PKT_PING:
                    trace = self.input_trace
                    received = time.perf_counter_ns() if trace is not None and trace.enabled else 0
                    sending = time.perf_counter_ns() if received else 0
                    await self._write_packet(writer, PKT_PONG, seq)
                    if received:
                        trace.packet(trace_session, seq, 0, received, sending,
                                     time.perf_counter_ns(), payload, kind=6)
                else:
                    raise ValueError("Authentication cannot be repeated within a session")
                now = time.monotonic()
                elapsed = now - self._last_stats_time
                if elapsed >= 1:
                    self._callback(self.on_stats, self.stats_events_count / elapsed,
                                   self.stats_packets_count, self.total_events_count)
                    self.stats_events_count = self.stats_packets_count = 0
                    self._last_stats_time = now
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.TimeoutError):
            logger.info("Client connection ended: %s", address)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError) as error:
            logger.warning("Closing client %s: %s", address, error)
        except Exception:
            logger.exception("Unexpected input-session failure")
        finally:
            if owned:
                self._owner = None
                self.active_clients.discard(address)
                reset = getattr(self.tablet, "reset", None)
                if reset:
                    try:
                        reset()
                    except Exception as error:
                        logger.error("Unable to release input state", exc_info=True)
                        self._fail_device(error)
                self._callback(self.on_client_disconnected, address)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), self.shutdown_timeout)
            except (OSError, asyncio.TimeoutError):
                writer.transport.abort()
            finally:
                self._writers.discard(writer)
                self._handlers.discard(task)

    def _fail_device(self, error):
        if self._device_failed:
            return
        self._device_failed = True
        self._running = False
        close = getattr(self.tablet, "close", None)
        if close:
            try:
                close()
            except Exception:
                logger.error("Unable to close failed input device", exc_info=True)
        if self.on_device_error:
            self._callback(self.on_device_error, str(error))
        else:
            # Standalone users have no worker orchestrator to request cleanup.
            task = asyncio.create_task(self.stop())
            task.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)

    def _dispatch_event_groups(self, groups):
        """Preserve every sample and transition, including pressure extrema.

        Backlog control belongs at the session queue/admission boundary; dropping
        already-received coordinates here silently changes the drawn stroke.
        """
        for events in groups:
            for event in events:
                self.tablet.handle_event(event)
                self.stats_events_count += 1
                self.total_events_count += 1

    @property
    def bound_endpoint(self):
        return self.server.getsockname()[:2] if self.server else None

    async def _accept(self):
        loop = asyncio.get_running_loop()
        while self._running:
            connection, _ = await loop.sock_accept(self.server)
            connection.setblocking(False)
            # Admission happens before any TLS state or handshake task exists.
            if len(self._handlers) >= self.max_connections:
                connection.close()
                await asyncio.sleep(0.01)
                continue
            self._connections.add(connection)
            task = asyncio.create_task(self._serve_socket(connection))
            self._handlers.add(task)

    async def _serve_socket(self, connection):
        transport = None
        task = asyncio.current_task()
        try:
            loop = asyncio.get_running_loop()
            reader = asyncio.StreamReader(limit=65544)
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await loop.connect_accepted_socket(
                lambda: protocol, connection, ssl=self.tls_context,
                ssl_handshake_timeout=self.handshake_timeout)
            writer = asyncio.StreamWriter(transport, protocol, reader, loop)
            await self._handle_client(reader, writer)
        except (OSError, asyncio.TimeoutError):
            logger.debug("TLS handshake closed")
        finally:
            if transport:
                transport.abort()
            connection.close()
            self._connections.discard(connection)
            self._handlers.discard(task)

    async def start(self):
        if self.server is not None:
            return
        if self.tls_context is None or self.pairing_code is None:
            raise ValueError("A TLS identity and pairing code are required")
        auth_proof(self.pairing_code, b"\0" * NONCE_SIZE, "server")
        loop = asyncio.get_running_loop()
        addresses = await loop.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM,
                                           flags=socket.AI_PASSIVE)
        family, kind, proto, _, address = addresses[0]
        listener = socket.socket(family, kind, proto)
        try:
            if sys.platform != "win32":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.setblocking(False)
            listener.bind(address)
            listener.listen(16)
        except BaseException:
            listener.close()
            raise
        self.server = listener
        self._device_failed = False
        self._running = True
        self._accept_task = asyncio.create_task(self._accept())
        logger.info("TLS pen server listening on %s:%s", *self.bound_endpoint)

    async def stop(self):
        """Close raw handshakes and authenticated sessions on every supported Python."""
        async with self._stop_lock:
            self._running = False
            listener, self.server = self.server, None
            try:
                if self._accept_task:
                    self._accept_task.cancel()
                    await asyncio.gather(self._accept_task, return_exceptions=True)
                    self._accept_task = None
            finally:
                # Await sock_accept cancellation before releasing the listener
                # FD, even when stop itself is cancelled. Deferred reader
                # cleanup must not unregister a new pipe/child watcher using it.
                if listener:
                    listener.close()
            for connection in tuple(self._connections):
                connection.close()
            for writer in tuple(self._writers):
                writer.transport.abort()
            handlers = self._handlers - {asyncio.current_task()}
            for task in handlers:
                task.cancel()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers, return_exceptions=True),
                                       self.shutdown_timeout * 2)
            self._callback(self.on_stats, 0.0, 0, self.total_events_count)
