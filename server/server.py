"""
Asynchronous TCP server for S Pen events.
Receives high-frequency stylus motion events over TCP and forwards them
to the virtual tablet subsystem with minimal latency (TCP_NODELAY enabled).
Supports status callbacks for GUI integration.
"""

import asyncio
import logging
import socket
import time
from typing import Optional, Callable

from server.protocol import (
    HEADER_SIZE,
    PKT_EVENT,
    PKT_PING,
    PKT_PONG,
    PKT_HANDSHAKE,
    ACTION_HOVER_MOVE,
    ACTION_MOVE,
    unpack_header,
    unpack_events,
    pack_packet,
)
from server.virtual_tablet import VirtualTablet

logger = logging.getLogger("SPenServer")


class SPenServer:
    def __init__(
        self,
        tablet: VirtualTablet,
        host: str = "0.0.0.0",
        port: int = 40118,
        on_client_connected: Optional[Callable[[str], None]] = None,
        on_client_disconnected: Optional[Callable[[str], None]] = None,
        on_stats: Optional[Callable[[float, int, int], None]] = None,
    ):
        self.tablet = tablet
        self.host = host
        self.port = port
        self.on_client_connected = on_client_connected
        self.on_client_disconnected = on_client_disconnected
        self.on_stats = on_stats

        self.server: Optional[asyncio.Server] = None
        self._running = False
        self.active_clients = set()

        # Stats
        self.stats_events_count = 0
        self.stats_packets_count = 0
        self.total_events_count = 0
        self._last_stats_time = time.time()

    @property
    def is_running(self) -> bool:
        return self._running and self.server is not None

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "Unknown"
        logger.info(f"Client connected from {peer_str}")
        self.active_clients.add(peer_str)

        if self.on_client_connected:
            try:
                self.on_client_connected(peer_str)
            except Exception as e:
                logger.debug(f"Error in on_client_connected callback: {e}")

        # Configure socket for ultra-low latency
        sock: Optional[socket.socket] = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        buffer = bytearray()

        try:
            while self._running:
                chunk = await reader.read(4096)
                if not chunk:
                    logger.info(f"Client {peer_str} disconnected (EOF)")
                    break

                # Re-arm TCP_QUICKACK after every read. Linux reverts a socket to
                # delayed ACKs once it's judged the connection idle, and the ~40ms
                # delayed-ACK timer is a real, avoidable source of jitter for a
                # live pen-position stream over Wi-Fi. No-op on platforms without it.
                if sock is not None and hasattr(socket, "TCP_QUICKACK"):
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
                    except OSError:
                        pass

                buffer.extend(chunk)

                # Drain every complete packet currently buffered. PKT_EVENT payloads
                # are collected rather than dispatched immediately so a Wi-Fi
                # backlog (several packets arriving in this one read()) can be
                # coalesced below instead of replayed as visible catch-up lag.
                event_groups = []
                while len(buffer) >= HEADER_SIZE:
                    hdr_res = unpack_header(buffer[:HEADER_SIZE])
                    if hdr_res is None:
                        # Corrupted or non-protocol data: discard 1 byte to seek next magic
                        buffer.pop(0)
                        continue

                    pkt_type, seq, payload_len = hdr_res
                    total_len = HEADER_SIZE + payload_len

                    if len(buffer) < total_len:
                        # Wait for remaining payload bytes
                        break

                    # Slice out packet
                    payload = buffer[HEADER_SIZE:total_len]
                    del buffer[:total_len]

                    # Handle packet type
                    if pkt_type == PKT_EVENT:
                        events = unpack_events(payload)
                        event_groups.append(events)
                        self.stats_packets_count += 1

                    elif pkt_type == PKT_PING:
                        # Sent/drained immediately even though PKT_EVENT dispatch below is
                        # deferred to the end of this drain pass: a PONG here is only an
                        # a link-liveness ack, not a "prior events applied" guarantee. If a
                        # PING/PONG-based RTT measurement is ever added, re-check this
                        # ordering against _dispatch_event_groups()'s deferred dispatch.
                        pong = pack_packet(PKT_PONG, seq, b"")
                        writer.write(pong)
                        await writer.drain()

                    elif pkt_type == PKT_HANDSHAKE:
                        logger.info(f"Handshake packet received from {peer_str}")
                        ack = pack_packet(PKT_HANDSHAKE, seq, b"OK")
                        writer.write(ack)
                        await writer.drain()

                if event_groups:
                    self._dispatch_event_groups(event_groups)

                # Periodic stats logging and callback (every 1.0 second)
                now = time.time()
                elapsed = now - self._last_stats_time
                if elapsed >= 1.0:
                    rate = self.stats_events_count / elapsed
                    if self.on_stats:
                        try:
                            self.on_stats(rate, self.stats_packets_count, self.total_events_count)
                        except Exception:
                            pass
                    if self.stats_events_count > 0:
                        logger.info(f"Traffic: {rate:.1f} events/sec ({self.stats_packets_count} packets)")
                    self.stats_events_count = 0
                    self.stats_packets_count = 0
                    self._last_stats_time = now

        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.error(f"Error handling client {peer_str}: {err}")
        finally:
            logger.info(f"Closing client connection {peer_str}")
            self.active_clients.discard(peer_str)
            if self.on_client_disconnected:
                try:
                    self.on_client_disconnected(peer_str)
                except Exception as e:
                    logger.debug(f"Error in on_client_disconnected callback: {e}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _dispatch_event_groups(self, groups):
        """Forward received pen events to the virtual tablet, coalescing a
        Wi-Fi backlog when one has formed.

        Each element of `groups` is the list of PenEvent objects unpacked from
        one received network packet, in arrival order. Normally there is only
        ever one packet's worth of events per read() (the Android client
        flushes on every touch/hover callback), so this is a plain pass-through.
        But if delivery stalls for a moment - a Wi-Fi hiccup, a brief scheduling
        delay - the OS can hand us several already-queued packets in a single
        read(). Replaying every buffered position sample in order in that case
        makes the on-screen cursor visibly "catch up in slow motion" instead of
        jumping straight to where the pen actually is right now.

        A pure position/pressure sample (ACTION_MOVE / ACTION_HOVER_MOVE) is
        safe to drop only when it is the LAST event of its own packet and is
        immediately superseded by the first event of the NEXT already-arrived
        packet carrying the same action, the same button state, and the same
        tool type - i.e. it was already stale the moment we got to it, and
        skipping it changes nothing but which position sample got acted on.
        This never skips anything within a single packet (preserving the
        historical-sample batching Android provides for stroke fidelity),
        never skips a press/release/proximity transition, a button-state
        change, or a tool-type change (stylus/eraser), and never skips the
        very last event overall (the freshest sample always gets delivered).

        stats_events_count/total_events_count are incremented here (per event
        actually forwarded to the tablet), not while draining the socket, so
        the GUI's live "events/sec" reflects what the cursor actually did —
        not how many samples arrived over the wire before coalescing.
        """
        flat = [(group_idx, ev) for group_idx, group in enumerate(groups) for ev in group]
        last_idx = len(flat) - 1
        dispatched = 0
        for i, (group_idx, ev) in enumerate(flat):
            if ev.action in (ACTION_HOVER_MOVE, ACTION_MOVE) and i < last_idx:
                next_group_idx, next_ev = flat[i + 1]
                if (
                    next_group_idx != group_idx
                    and next_ev.action == ev.action
                    and next_ev.buttons == ev.buttons
                    and next_ev.tool_type == ev.tool_type
                ):
                    continue  # superseded by an already-arrived newer packet
            self.tablet.handle_event(ev)
            dispatched += 1
        self.stats_events_count += dispatched
        self.total_events_count += dispatched

    async def start(self):
        """Start listening for client connections."""
        self._running = True
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        addrs = ", ".join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f"SPen Server listening on {addrs}")

    async def stop(self):
        """Stop server gracefully."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            logger.info("SPen Server stopped")
