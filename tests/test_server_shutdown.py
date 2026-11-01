"""Regression for listener FD reuse while pending accept cancellation unwinds."""

import asyncio
import os
import sys
import tempfile
import unittest

from server.security import load_identity
from server.server import SPenServer


@unittest.skipIf(sys.platform == "win32", "Requires a selector event loop")
class ListenerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_listener_cancellation_cannot_unregister_reused_descriptor(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = load_identity(folder)
            server = SPenServer(
                None,
                port=0,
                tls_context=identity.server_context(),
                pairing_code=identity.pairing_code,
            )
            await server.start()
            # Let sock_accept register its reader on the original listener.
            await asyncio.sleep(0)
            loop = asyncio.get_running_loop()
            original = server.server
            notified = loop.create_future()
            descriptors = []

            class ReuseOnClose:
                def close(self):
                    old_fd = original.fileno()
                    original.close()
                    reader, writer = os.pipe()
                    descriptors.extend((reader, writer))
                    self.assert_same_fd = reader == old_fd

                    def ready():
                        os.read(reader, 1)
                        loop.remove_reader(reader)
                        if not notified.done():
                            notified.set_result(True)

                    loop.add_reader(reader, ready)
                    os.write(writer, b"x")

            proxy = ReuseOnClose()
            server.server = proxy
            try:
                await server.stop()
                self.assertTrue(
                    proxy.assert_same_fd, "Test must exercise actual FD reuse"
                )
                self.assertTrue(await asyncio.wait_for(notified, 0.25))
            finally:
                if descriptors:
                    loop.remove_reader(descriptors[0])
                    for fd in descriptors:
                        os.close(fd)
                await server.stop()

    async def test_cancelled_stop_still_closes_listener_after_accept_unwinds(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = load_identity(folder)
            server = SPenServer(
                None,
                port=0,
                tls_context=identity.server_context(),
                pairing_code=identity.pairing_code,
            )
            await server.start()
            await asyncio.sleep(0)
            original = server.server
            stopping = asyncio.create_task(server.stop())
            asyncio.get_running_loop().call_soon(stopping.cancel)
            try:
                with self.assertRaises(asyncio.CancelledError):
                    await stopping
                self.assertEqual(original.fileno(), -1)
                self.assertTrue(server._accept_task.done())
            finally:
                await server.stop()
