"""Frame deadline and cancellation regressions; no OS input."""
import asyncio

import unittest

from server.protocol import PKT_HANDSHAKE, pack_packet
from server.server import SPenServer, _Budget


async def slow_frame(prefix):
    server = SPenServer(None)
    reader = asyncio.StreamReader()
    packet = pack_packet(PKT_HANDSHAKE, 0, bytes(36))

    reader.feed_data(packet[:prefix])

    async def feed():
        for byte in packet[prefix:]:
            await asyncio.sleep(0.01)
            reader.feed_data(bytes([byte]))

    feeder = asyncio.create_task(feed())
    try:
        with unittest.TestCase().assertRaises(asyncio.TimeoutError):
            await server._read_packet(reader, 0.025, _Budget(1000))
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


class PacketDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_frame(self):
        for prefix in (0, 9):
            with self.subTest(prefix=prefix):
                await slow_frame(prefix)

    async def test_external_cancellation(self):
        server = SPenServer(None)
        reader = asyncio.StreamReader()
        task = asyncio.create_task(server._read_packet(reader, 10, _Budget(1000)))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
