"""Real native relay + TLS receiver, simulated USB; never creates input devices."""

import asyncio
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from server.protocol import (
    ACTION_DOWN,
    ACTION_HOVER_MOVE,
    HEADER_SIZE,
    PKT_HANDSHAKE,
    PKT_PING,
    PKT_PONG,
    PenEvent,
    pack_events,
    pack_packet,
    unpack_header,
)
from server.security import AUTH_VERSION, auth_proof, load_identity
from server.server import SPenServer

ROOT = Path(__file__).resolve().parents[1]


class Sink:
    def __init__(self):
        self.events = []
        self.resets = 0

    def handle_event(self, event):
        self.events.append(event)

    def reset(self):
        self.resets += 1


def exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError()
        data.extend(chunk)
    return bytes(data)


def packet(stream):
    kind, seq, size = unpack_header(exact(stream, HEADER_SIZE))
    return kind, seq, exact(stream, size)


class NativeUsbRelayTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux":
            raise unittest.SkipTest("Native USB prototype targets Linux")
        compiler = shutil.which(os.environ.get("CC", "cc"))
        if not compiler:
            raise unittest.SkipTest("C compiler unavailable")
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.directory.name) / "relay-fixture"
        sanitizer = (
            ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            if os.environ.get("SPEN_RELAY_SANITIZE") == "1"
            else []
        )
        subprocess.run(
            [
                compiler,
                *sanitizer,
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-I",
                str(ROOT / "native/usb-relay"),
                str(ROOT / "native/usb-relay/relay.c"),
                str(ROOT / "tests/native/usb_relay_fixture.c"),
                "-o",
                str(cls.binary),
            ],
            check=True,
            capture_output=True,
        )
        cls.identity = load_identity(Path(cls.directory.name) / "identity")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_production_descriptor_selection_excludes_adb_and_ambiguity(self):
        if not shutil.which("pkg-config"):
            self.skipTest("libusb build metadata unavailable")
        flags = subprocess.run(
            ["pkg-config", "--cflags", "--libs", "libusb-1.0"],
            capture_output=True,
            text=True,
        )
        if flags.returncode:
            self.skipTest("libusb development headers unavailable")
        target = Path(self.directory.name) / "descriptor-fixture"
        compiler = shutil.which(os.environ.get("CC", "cc"))
        sanitizer = (
            ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            if os.environ.get("SPEN_RELAY_SANITIZE") == "1"
            else []
        )
        subprocess.run(
            [
                compiler,
                *sanitizer,
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                str(ROOT / "tests/native/usb_descriptor_fixture.c"),
                str(ROOT / "native/usb-relay/relay.c"),
                *shlex.split(flags.stdout),
                "-o",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run([str(target)], check=True, capture_output=True, timeout=3)

    def start_relay(self, host, usb, mode=0, seconds=5):
        return subprocess.Popen(
            [
                str(self.binary),
                str(host.fileno()),
                str(usb.fileno()),
                str(mode),
                str(seconds),
            ],
            pass_fds=(host.fileno(), usb.fileno()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    async def test_tls_pairing_and_order_survive_partial_timeout_transfers(self):
        sink = Sink()
        server = SPenServer(
            sink,
            port=0,
            tls_context=self.identity.server_context(),
            pairing_code=self.identity.pairing_code,
        )
        await server.start()
        host = socket.create_connection(server.bound_endpoint)
        usb, phone = socket.socketpair()
        relay = self.start_relay(host, usb, mode=1, seconds=10)
        host.close()
        usb.close()
        stream = None
        try:

            def client():
                nonlocal stream
                phone.settimeout(3)
                stream = self.identity.client_context().wrap_socket(
                    phone, server_hostname="localhost"
                )
                kind, seq, challenge = packet(stream)
                self.assertEqual(
                    (kind, seq, challenge[:4]), (PKT_HANDSHAKE, 0, AUTH_VERSION)
                )
                nonce = challenge[4:]
                stream.sendall(
                    pack_packet(
                        PKT_HANDSHAKE,
                        0,
                        auth_proof(self.identity.pairing_code, nonce, "client"),
                    )
                )
                self.assertEqual(
                    packet(stream),
                    (
                        PKT_HANDSHAKE,
                        0,
                        auth_proof(self.identity.pairing_code, nonce, "server"),
                    ),
                )
                for index in range(300):
                    stream.sendall(
                        pack_events(
                            [PenEvent(ACTION_HOVER_MOVE, 0, 0, index / 1000, 0.5, 0)],
                            index,
                        )
                    )
                stream.sendall(pack_packet(PKT_PING, 501, b""))
                self.assertEqual(packet(stream), (PKT_PONG, 501, b""))

            await asyncio.to_thread(client)
            self.assertEqual([round(e.x * 1000) for e in sink.events], list(range(300)))
            # Close the receiver side to exercise normal socket EOF cleanup.
            await server.stop()
            out, err = await asyncio.to_thread(relay.communicate, timeout=2)
            self.assertEqual(err, b"")
            stats = json.loads(out)
            self.assertGreater(stats["to_host"], 300 * 24)
            self.assertGreater(stats["to_usb"], 100)
            self.assertEqual(sink.resets, 1)
        finally:
            if stream:
                stream.close()
            phone.close()
            if relay.poll() is None:
                relay.kill()
                await asyncio.to_thread(relay.communicate)
            await server.stop()

    async def test_relay_does_not_bypass_pairing(self):
        sink = Sink()
        server = SPenServer(
            sink,
            port=0,
            tls_context=self.identity.server_context(),
            pairing_code=self.identity.pairing_code,
        )
        await server.start()
        host = socket.create_connection(server.bound_endpoint)
        usb, phone = socket.socketpair()
        relay = self.start_relay(host, usb, seconds=5)
        host.close()
        usb.close()

        def client():
            phone.settimeout(2)
            with self.identity.client_context().wrap_socket(
                phone, server_hostname="localhost"
            ) as stream:
                _, _, challenge = packet(stream)
                bad_code = (
                    "A" if self.identity.pairing_code[0] != "A" else "B"
                ) + self.identity.pairing_code[1:]
                stream.sendall(
                    pack_packet(
                        PKT_HANDSHAKE, 0, auth_proof(bad_code, challenge[4:], "client")
                    )
                )
                self.assertEqual(stream.recv(1), b"")

        try:
            await asyncio.to_thread(client)
            await asyncio.to_thread(relay.communicate, timeout=2)
            self.assertEqual(sink.events, [])
            self.assertEqual(sink.resets, 0)
        finally:
            phone.close()
            if relay.poll() is None:
                relay.kill()
                await asyncio.to_thread(relay.communicate)
            await server.stop()

    async def test_multibuffer_bytes_preserved_and_zero_usb_packets_are_not_eof(self):
        for mode in (1, 4):
            with self.subTest(mode=mode):
                host, receiver = socket.socketpair()
                usb, phone = socket.socketpair()
                relay = self.start_relay(host, usb, mode=mode, seconds=5)
                host.close()
                usb.close()
                receiver.settimeout(3)
                phone.settimeout(3)
                upstream = bytes(range(256)) * 300
                downstream = upstream[::-1]
                try:

                    def exchange():
                        receiver.sendall(downstream)
                        phone.sendall(upstream)
                        self.assertEqual(exact(receiver, len(upstream)), upstream)
                        self.assertEqual(exact(phone, len(downstream)), downstream)

                    await asyncio.to_thread(exchange)
                    receiver.close()
                    out, err = await asyncio.to_thread(relay.communicate, timeout=2)
                    self.assertEqual(err, b"")
                    self.assertEqual(
                        json.loads(out),
                        dict(to_host=len(upstream), to_usb=len(downstream), error=0),
                    )
                finally:
                    receiver.close()
                    phone.close()
                    if relay.poll() is None:
                        relay.kill()
                        await asyncio.to_thread(relay.communicate)

    async def exercise(self, mode, seconds, send=b""):
        host, receiver = socket.socketpair()
        usb, phone = socket.socketpair()
        relay = self.start_relay(host, usb, mode=mode, seconds=seconds)
        host.close()
        usb.close()
        start = time.monotonic()
        try:
            if send:
                receiver.sendall(send)
            out, err = await asyncio.to_thread(relay.communicate, timeout=seconds + 2)
            self.assertEqual(err, b"")
            return json.loads(out), time.monotonic() - start, relay.returncode
        finally:
            receiver.close()
            phone.close()
            if relay.poll() is None:
                relay.kill()
                await asyncio.to_thread(relay.communicate)

    async def test_idle_lifetime_is_bounded(self):
        stats, elapsed, code = await self.exercise(0, 1)
        self.assertEqual(stats, dict(to_host=0, to_usb=0, error=0))
        self.assertEqual(code, 0)
        self.assertLess(elapsed, 2)

    async def test_invalid_bulk_progress_fails_and_joins_workers(self):
        stats, elapsed, code = await self.exercise(2, 5)
        self.assertEqual(stats["error"], -4)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, 1)

    async def test_stalled_usb_write_is_bounded(self):
        stats, elapsed, code = await self.exercise(3, 5, b"not pen input")
        self.assertEqual(stats["error"], -7)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, 3)

    async def test_peer_timeout_releases_owner_but_heartbeats_keep_it_live(self):
        sink = Sink()
        server = SPenServer(
            sink,
            port=0,
            tls_context=self.identity.server_context(),
            pairing_code=self.identity.pairing_code,
            idle_timeout=10,
        )
        await server.start()
        host = socket.create_connection(server.bound_endpoint)
        usb, phone = socket.socketpair()
        relay = self.start_relay(host, usb, seconds=15)
        host.close()
        usb.close()
        stream = None
        try:

            def client():
                nonlocal stream
                phone.settimeout(3)
                stream = self.identity.client_context().wrap_socket(
                    phone, server_hostname="localhost"
                )
                _, _, challenge = packet(stream)
                stream.sendall(
                    pack_packet(
                        PKT_HANDSHAKE,
                        0,
                        auth_proof(self.identity.pairing_code, challenge[4:], "client"),
                    )
                )
                self.assertEqual(
                    packet(stream),
                    (
                        PKT_HANDSHAKE,
                        0,
                        auth_proof(self.identity.pairing_code, challenge[4:], "server"),
                    ),
                )
                stream.sendall(
                    pack_events([PenEvent(ACTION_DOWN, 0, 0, 0.5, 0.5, 0.7)])
                )
                for seq in range(4):
                    time.sleep(1)
                    stream.sendall(pack_packet(PKT_PING, seq, b""))
                    self.assertEqual(packet(stream), (PKT_PONG, seq, b""))
                    self.assertEqual(sink.resets, 0)

            await asyncio.to_thread(client)
            self.assertIsNotNone(server._owner)
            self.assertEqual(len(sink.events), 1)
            # Keep the simulated USB socket and TLS client open: this models
            # a stopped helper with cable/device still attached and no USB EOF.
            silent_since = time.monotonic()
            out, err = await asyncio.to_thread(relay.communicate, timeout=4.5)
            self.assertEqual(err, b"")
            self.assertEqual(json.loads(out)["error"], -9)
            self.assertEqual(relay.returncode, 1)
            self.assertLess(time.monotonic() - silent_since, 4.5)
            deadline = time.monotonic() + 0.5
            while sink.resets == 0 and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            self.assertEqual(sink.resets, 1)
            self.assertIsNone(server._owner)
        finally:
            if stream:
                stream.close()
            phone.close()
            if relay.poll() is None:
                relay.kill()
                await asyncio.to_thread(relay.communicate)
            await server.stop()

    async def test_downstream_bytes_cannot_keep_a_dead_phone_live(self):
        host, receiver = socket.socketpair()
        usb, phone = socket.socketpair()
        relay = self.start_relay(host, usb, seconds=10)
        host.close()
        usb.close()
        receiver.settimeout(1)
        phone.settimeout(1)
        start = time.monotonic()

        def traffic():
            count = 0
            try:
                while time.monotonic() - start < 4:
                    receiver.sendall(b"host-only")
                    if exact(phone, 9) != b"host-only":
                        raise AssertionError("Downstream bytes changed")
                    count += 1
                    time.sleep(0.1)
            except (OSError, EOFError):
                pass
            return count

        try:
            count = await asyncio.to_thread(traffic)
            out, err = await asyncio.to_thread(relay.communicate, timeout=1)
            self.assertGreater(count, 10)
            self.assertEqual(err, b"")
            self.assertEqual(json.loads(out)["error"], -9)
            self.assertLess(time.monotonic() - start, 4.5)
        finally:
            receiver.close()
            phone.close()
            if relay.poll() is None:
                relay.kill()
                await asyncio.to_thread(relay.communicate)
