"""Short loopback TLS admission/reconnect stress check. Uses no OS input backend."""
import asyncio
import gc
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.protocol import ACTION_MOVE, HEADER_SIZE, PKT_HANDSHAKE, PKT_PING, PKT_PONG, PenEvent, pack_events, pack_packet, unpack_header
from server.security import auth_proof, load_identity
from server.server import SPenServer


class Counter:
    def __init__(self):
        self.count = self.resets = 0
        self.held = False
    def handle_event(self, event):
        self.count += 1
        self.held = bool(event.buttons)
    def reset(self):
        self.resets += 1
        self.held = False
    def close(self):
        self.reset()


async def main():
    tablet = Counter()
    expected = peak_handlers = 0
    latencies = []
    with tempfile.TemporaryDirectory() as directory:
        identity = load_identity(directory)
        context = identity.client_context()
        server = SPenServer(tablet, port=0, tls_context=identity.server_context(),
                            pairing_code=identity.pairing_code, handshake_timeout=.5)
        await server.start()
        port = server.bound_endpoint[1]
        fd_start = len(list(Path('/proc/self/fd').iterdir()))

        async def packet(reader):
            kind, seq, size = unpack_header(await asyncio.wait_for(reader.readexactly(HEADER_SIZE), 2))
            return kind, seq, await asyncio.wait_for(reader.readexactly(size), 2)

        async def connect():
            reader, writer = await asyncio.open_connection('127.0.0.1', port, ssl=context, server_hostname='localhost')
            kind, seq, challenge = await packet(reader)
            assert (kind, seq, len(challenge)) == (PKT_HANDSHAKE, 0, 36)
            writer.write(pack_packet(PKT_HANDSHAKE, 0, auth_proof(identity.pairing_code, challenge[4:], 'client')))
            await writer.drain()
            assert await packet(reader) == (PKT_HANDSHAKE, 0, auth_proof(identity.pairing_code, challenge[4:], 'server'))
            return reader, writer

        async def release(writer):
            writer.close()
            await writer.wait_closed()
            for _ in range(200):
                if not server.active_clients:
                    assert not tablet.held
                    return
                await asyncio.sleep(.005)
            raise AssertionError('Owner did not release')

        flood_writers = []
        async def flood():
            for _ in range(120):
                try:
                    _, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), .1)
                    writer.write(b'\x16')  # Incomplete TLS handshake; never authenticated.
                    flood_writers.append(writer)
                except (OSError, asyncio.TimeoutError):
                    pass
                await asyncio.sleep(.005)

        writer = attack = None
        started = time.monotonic()
        try:
            reader, writer = await connect()
            attack = asyncio.create_task(flood())
            for seq in range(100):
                events = [PenEvent(ACTION_MOVE, 0, 4, i / 23, .5, i / 23) for i in range(24)]
                writer.write(pack_events(events, seq))
                expected += len(events)
                if seq % 10 == 0:
                    ping_start = time.monotonic()
                    writer.write(pack_packet(PKT_PING, seq, b''))
                    await writer.drain()
                    assert await packet(reader) == (PKT_PONG, seq, b'')
                    latencies.append(time.monotonic() - ping_start)
                peak_handlers = max(peak_handlers, len(server._handlers))
                assert len(server._handlers) <= server.max_connections
                await asyncio.sleep(.02)
            await attack
            for peer in flood_writers:
                peer.close()
            await asyncio.gather(*(peer.wait_closed() for peer in flood_writers), return_exceptions=True)
            await release(writer)
            await asyncio.sleep(.6)
            for seq in range(80):
                reader, writer = await connect()
                writer.write(pack_events([PenEvent(ACTION_MOVE, 0, 4, .5, .5, .7)] * 96, seq))
                expected += 96
                writer.write(pack_packet(PKT_PING, seq, b''))
                await writer.drain()
                assert await packet(reader) == (PKT_PONG, seq, b'')
                await release(writer)
            assert tablet.count == expected, (tablet.count, expected)
        finally:
            if attack and not attack.done():
                attack.cancel()
                await asyncio.gather(attack, return_exceptions=True)
            if writer:
                writer.close()
            for peer in flood_writers:
                peer.close()
            shutdown = time.monotonic()
            await server.stop()
            shutdown = time.monotonic() - shutdown
        gc.collect()
        await asyncio.sleep(.1)
        fd_end = len(list(Path('/proc/self/fd').iterdir()))
        assert fd_end <= fd_start + 1, (fd_start, fd_end)
        assert not server._handlers and not server._connections and not server._writers
        report = dict(events=tablet.count, expected=expected, authenticated_sessions=81,
                      resets=tablet.resets, incomplete_tls_attempts=120, peak_handlers=peak_handlers,
                      maximum_handlers=server.max_connections, peak_ping_seconds=max(latencies),
                      shutdown_seconds=shutdown, elapsed_seconds=time.monotonic()-started,
                      fd_before=fd_start, fd_after=fd_end, desktop_events_sent=False)
        Path('audit/evidence/remediation-session-stress.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
