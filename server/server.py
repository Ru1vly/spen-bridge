"""
Asynchronous TCP server for S Pen events.
Receives high-frequency stylus motion events over TCP and forwards them
to the virtual tablet subsystem with minimal latency (TCP_NODELAY enabled).
"""

import asyncio
import logging
import socket
import time
from typing import Optional

from server.protocol import (
    HEADER_SIZE,
    PKT_EVENT,
    PKT_PING,
    PKT_PONG,
    PKT_HANDSHAKE,
    unpack_header,
    unpack_events,
    pack_packet,
)
from server.virtual_tablet import VirtualTablet

logger = logging.getLogger("SPenServer")


class SPenServer:
    def __init__(self, tablet: VirtualTablet, host: str = "0.0.0.0", port: int = 40118):
        self.tablet = tablet
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self._running = False
        self.stats_events_count = 0
        self.stats_packets_count = 0
        self._last_stats_time = time.time()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        logger.info(f"Client connected from {peer}")

        # Configure socket for ultra-low latency
        sock: Optional[socket.socket] = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        buffer = bytearray()

        try:
            while self._running:
                chunk = await reader.read(4096)
                if not chunk:
                    logger.info(f"Client {peer} disconnected (EOF)")
                    break

                buffer.extend(chunk)

                # Process all complete packets in buffer
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
                        for ev in events:
                            self.tablet.handle_event(ev)
                        self.stats_events_count += len(events)
                        self.stats_packets_count += 1

                    elif pkt_type == PKT_PING:
                        pong = pack_packet(PKT_PONG, seq, b"")
                        writer.write(pong)
                        await writer.drain()

                    elif pkt_type == PKT_HANDSHAKE:
                        logger.info(f"Handshake packet received from {peer}")
                        ack = pack_packet(PKT_HANDSHAKE, seq, b"OK")
                        writer.write(ack)
                        await writer.drain()

                # Periodic stats logging (every 5 seconds)
                now = time.time()
                elapsed = now - self._last_stats_time
                if elapsed >= 5.0 and self.stats_events_count > 0:
                    rate = self.stats_events_count / elapsed
                    logger.info(f"Traffic: {rate:.1f} events/sec ({self.stats_packets_count} packets)")
                    self.stats_events_count = 0
                    self.stats_packets_count = 0
                    self._last_stats_time = now

        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.error(f"Error handling client {peer}: {err}")
        finally:
            logger.info(f"Closing client connection {peer}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

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
            logger.info("SPen Server stopped")
