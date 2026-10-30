"""Desired-behavior regressions for audit findings; no OS input is injected."""
import asyncio
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from server import config as configuration
from server.backends.base import TabletBackendBase
from server.config import TabletConfig
from server.protocol import (
    ACTION_CANCEL, ACTION_DOWN, ACTION_HOVER_EXIT, ACTION_MOVE,
    ACTION_UP, BUTTON_STYLUS, EVENT_STRUCT, HEADER_SIZE,
    MAX_EVENTS_PER_PACKET, PKT_EVENT, PKT_HANDSHAKE, PKT_PING, PKT_PONG,
    PenEvent, pack_events, pack_packet, unpack_events, unpack_header,
)
from server.security import AUTH_VERSION, auth_proof, load_identity
from server.server import SPenServer
from server.settings import effective_settings, listener_address

EVENT = PenEvent(ACTION_DOWN, 0, 0, .5, .5, .5)


class MemoryTablet(TabletBackendBase):
    def _setup_device(self):
        self.events = []
        self.resets = 0

    def handle_event(self, event):
        self.events.append(event)

    def reset(self):
        self.resets += 1

    def _release_touch(self):
        pass

    def close(self):
        pass


class MappingTests(unittest.TestCase):
    def test_clear_region_restores_full_desktop(self):
        tablet = MemoryTablet(screen_bounds=(0, 0, 960, 1080), desktop_size=(1920, 1080))
        tablet.update_settings(screen_bounds=None, desktop_size=None)
        self.assertEqual(tablet._map_coordinates(1, 1), (65535, 65535))

    def test_omitted_mapping_update_retains_region(self):
        tablet = MemoryTablet(screen_bounds=(0, 0, 960, 1080), desktop_size=(1920, 1080))
        tablet.update_settings(pressure_gamma=2)
        self.assertEqual(tablet._map_coordinates(1, 1), (32767, 65535))

    def test_aspect_lock_fits_target_region_and_applies_live(self):
        tablet = MemoryTablet(desktop_size=(1920, 1080))
        tablet.update_settings(aspect_ratio_lock=True, tablet_aspect_ratio="4:3")
        self.assertEqual(tablet._map_coordinates(0, 0), (8191, 0))
        self.assertEqual(tablet._map_coordinates(1, 1), (57343, 65535))
        tablet.update_settings(screen_bounds=(960, 0, 960, 1080))
        # Fitted target: 960x720 centered vertically in the right-hand region.
        self.assertEqual(tablet._map_coordinates(0, 0), (32767, 10922))

    def test_invalid_update_is_transactional(self):
        tablet = MemoryTablet()
        with self.assertRaises(ValueError):
            tablet.update_settings(pressure_gamma=3, desktop_size=(0, 0))
        self.assertEqual(tablet.pressure_gamma, 1)
        self.assertIsNone(tablet.desktop_size)

    def test_cli_gui_resolver_preserves_click_disable_and_selected_monitor(self):
        config = TabletConfig()
        config.click_on_touch = False
        config.mapping_mode = "monitor"
        config.selected_monitor = "right"
        detected = ([dict(name="right", x=1920, y=0, width=1920, height=1080)], (3840, 1080))
        resolved = effective_settings(config, detected)
        self.assertFalse(resolved["click_on_touch"])
        self.assertEqual(resolved["screen_bounds"], (1920, 0, 1920, 1080))
        self.assertEqual(resolved["desktop_size"], (3840, 1080))

    def test_xrandr_negative_offsets_are_not_omitted(self):
        from types import SimpleNamespace
        from server.monitors import get_monitors_from_xrandr
        result = SimpleNamespace(returncode=0, stdout=(
            "DP-1 connected 1280x720-1280-100\n"
            "HDMI-1 connected primary 1920x1080+0+0\n"))
        with patch("server.monitors.subprocess.run", return_value=result):
            monitors = get_monitors_from_xrandr()
        self.assertEqual(len(monitors), 2)
        self.assertEqual((monitors[0]["x"], monitors[0]["y"]), (-1280, -100))


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.json"
        self.patch = patch.object(configuration, "CONFIG_FILE_PATH", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_reject_invalid_types_ranges_and_nonfinite_values(self):
        for data in ([], {"port": -1}, {"port": True}, {"port": 10 ** 1000},
                     {"desktop_size": [0, 0]}, {"auto_start_server": "false"},
                     {"pressure_gamma": math.nan}, {"custom_bounds": [0, 0, -1, 20]},
                     {"profiles": []}, {"profiles": {"Default": None}}):
            with self.subTest(data=str(data)[:50]), self.assertRaises(ValueError):
                TabletConfig.from_dict(data)

    def test_legacy_profile_identity_is_canonical_and_default_restored(self):
        loaded = TabletConfig.from_dict({"active_profile_name": "missing",
                                        "profiles": {"Drawing": {"name": "old-name"}}})
        self.assertEqual(loaded.profiles["Drawing"].name, "Drawing")
        self.assertIn("Default", loaded.profiles)
        self.assertEqual(loaded.active_profile_name, "Default")

    def test_legacy_wildcard_does_not_enable_wifi(self):
        config = TabletConfig.from_dict({"host": "0.0.0.0"})
        self.assertEqual(listener_address(config), "127.0.0.1")
        config.wifi_enabled = True
        self.assertEqual(listener_address(config), "0.0.0.0")

    def test_failed_replace_preserves_original(self):
        config = TabletConfig()
        self.assertTrue(configuration.save_config(config))
        original = self.path.read_bytes()
        config.port += 1
        with patch("server.config.os.replace", side_effect=OSError("disk unavailable")):
            self.assertFalse(configuration.save_config(config))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".config*")), [])

    def test_corrupt_primary_recovers_backup_and_preserves_damaged_file(self):
        config = TabletConfig()
        configuration.save_config(config)
        config.port += 1
        configuration.save_config(config)
        self.path.write_text("{damaged", encoding="utf-8")
        recovered = configuration.load_config()
        self.assertEqual(recovered.port, 40118)
        self.assertTrue(recovered.recovery_notice)
        self.assertEqual(self.path.read_text(), "{damaged")
        preserved = list(self.path.parent.glob("config.json.corrupt-*"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_text(), "{damaged")
        configuration.save_config(recovered)
        self.assertEqual(json.loads(self.path.with_suffix(".json.bak").read_text())["port"], 40118)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


class StrictProtocolTests(unittest.TestCase):
    def test_invalid_batch_rejects_all_records(self):
        valid = pack_events([EVENT])[HEADER_SIZE:]
        invalid_records = [
            EVENT_STRUCT.pack(255, 0, 0, .5, .5, .5, 0, 0),
            EVENT_STRUCT.pack(3, 255, 0, .5, .5, .5, 0, 0),
            EVENT_STRUCT.pack(3, 0, 8, .5, .5, .5, 0, 0),
            EVENT_STRUCT.pack(3, 0, 0, math.nan, .5, .5, 0, 0),
            EVENT_STRUCT.pack(3, 0, 0, .5, .5, math.inf, 0, 0),
            EVENT_STRUCT.pack(3, 0, 0, 1.1, .5, .5, 0, 0),
            EVENT_STRUCT.pack(3, 0, 0, .5, .5, .5, 91, 0),
        ]
        for invalid in invalid_records:
            with self.subTest(record=invalid), self.assertRaises(ValueError):
                unpack_events(valid + invalid)

    def test_payload_limit_and_nan_cannot_serialize(self):
        self.assertEqual(len(unpack_events(pack_events([EVENT] * MAX_EVENTS_PER_PACKET)[HEADER_SIZE:])),
                         MAX_EVENTS_PER_PACKET)
        with self.assertRaises(ValueError):
            pack_events([EVENT] * (MAX_EVENTS_PER_PACKET + 1))
        with self.assertRaises(ValueError):
            pack_events([replace(EVENT, pressure=math.nan)])


try:
    import evdev
except ImportError:
    evdev = None


@unittest.skipIf(evdev is None, "evdev is unavailable on this OS")
class LinuxStateTests(unittest.TestCase):
    def setUp(self):
        from server.backends.linux_uinput import LinuxUinputTablet
        self.codes = evdev.ecodes
        self.tablet_type = LinuxUinputTablet
        # Bypass setup, so even constructing a backend cannot create a device.
        setup = patch.object(LinuxUinputTablet, "_setup_device")
        setup.start()
        self.addCleanup(setup.stop)
        self.tablet = LinuxUinputTablet()
        self.tablet.uinput = Mock()
        self.addCleanup(self.tablet.close)

    def pressed(self, code):
        writes = [c.args[2] for c in self.tablet.uinput.write.call_args_list
                  if c.args[:2] == (self.codes.EV_KEY, code)]
        return bool(writes[-1]) if writes else False

    def test_disconnect_reset_releases_tip_buttons_pressure_and_smoothing(self):
        self.tablet.handle_event(replace(EVENT, buttons=3))
        self.assertTrue(self.pressed(self.codes.BTN_LEFT))
        self.tablet.reset()
        for code in (self.codes.BTN_LEFT, self.codes.BTN_RIGHT, self.codes.BTN_MIDDLE, self.codes.BTN_TOUCH):
            self.assertFalse(self.pressed(code))
        self.assertFalse(self.tablet._is_down)
        self.assertIsNone(self.tablet._smooth_x)
        self.tablet.reset()

    def test_remap_releases_original_and_two_sources_share_an_output(self):
        self.tablet.handle_event(replace(EVENT, buttons=BUTTON_STYLUS))
        self.tablet.update_settings(button_primary="middle_click")
        self.assertFalse(self.pressed(self.codes.BTN_RIGHT))
        self.tablet.update_settings(button_primary="right_click", button_secondary="right_click")
        self.tablet.handle_event(replace(EVENT, buttons=3))
        self.tablet.handle_event(replace(EVENT, buttons=1, action=ACTION_MOVE))
        self.assertTrue(self.pressed(self.codes.BTN_RIGHT))
        self.tablet.handle_event(replace(EVENT, buttons=0, action=ACTION_UP))
        self.assertFalse(self.pressed(self.codes.BTN_RIGHT))

    def test_cancel_and_exit_ignore_held_wire_flags(self):
        for action in (ACTION_CANCEL, ACTION_HOVER_EXIT):
            self.tablet.handle_event(replace(EVENT, buttons=3))
            self.tablet.handle_event(replace(EVENT, action=action, buttons=3))
            self.assertEqual(self.tablet._held_codes, set())
            self.assertFalse(self.tablet._button_stylus_pressed)

    def test_invalid_event_never_reaches_device(self):
        for invalid in (replace(EVENT, action=255), replace(EVENT, pressure=math.nan),
                        replace(EVENT, buttons=8), replace(EVENT, x=1.1)):
            self.tablet.handle_event(invalid)
        self.tablet.uinput.write.assert_not_called()

    def test_physical_finger_has_same_single_pointer_policy(self):
        self.tablet.handle_event(replace(EVENT, tool_type=2))
        self.assertTrue(self.pressed(self.codes.BTN_LEFT))
        self.tablet.handle_event(replace(EVENT, tool_type=2, action=ACTION_UP))
        self.assertFalse(self.pressed(self.codes.BTN_LEFT))

    def test_tablet_disabled_and_eraser_actions(self):
        tablet = self.tablet_type(mode="tablet", button_primary="eraser", button_secondary="none")
        tablet.uinput = Mock()
        try:
            tablet.handle_event(replace(EVENT, buttons=3))
            self.assertTrue(tablet._eraser_latched)
            self.assertIn((self.codes.EV_KEY, self.codes.BTN_TOOL_RUBBER, 1),
                          [c.args for c in tablet.uinput.write.call_args_list])
            self.assertNotIn(self.codes.BTN_STYLUS2, tablet._held_codes)
            tablet.reset()
            self.assertFalse(tablet._eraser_latched)
        finally:
            tablet.close()

    def test_unsupported_pointer_actions_are_rejected_explicitly(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.tablet.update_settings(button_primary="eraser")


class SecureSessionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.identity = load_identity(cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    async def asyncSetUp(self):
        self.tablet = MemoryTablet()
        self.server = SPenServer(self.tablet, port=0,
                                 tls_context=self.identity.server_context(),
                                 pairing_code=self.identity.pairing_code,
                                 handshake_timeout=.4, idle_timeout=.3, shutdown_timeout=.4)
        await self.server.start()
        self.port = self.server.bound_endpoint[1]
        self.connections = []

    async def asyncTearDown(self):
        for _, writer in self.connections:
            writer.close()
        await self.server.stop()
        for _, writer in self.connections:
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, asyncio.TimeoutError):
                pass

    async def connect(self):
        pair = await asyncio.open_connection("127.0.0.1", self.port,
                                              ssl=self.identity.client_context(), server_hostname="localhost")
        self.connections.append(pair)
        return pair

    async def packet(self, reader):
        header = await asyncio.wait_for(reader.readexactly(HEADER_SIZE), 1)
        kind, seq, size = unpack_header(header)
        return kind, seq, await reader.readexactly(size)

    async def authenticate(self, pair, code=None):
        reader, writer = pair
        kind, seq, challenge = await self.packet(reader)
        self.assertEqual((kind, seq, challenge[:4]), (PKT_HANDSHAKE, 0, AUTH_VERSION))
        nonce = challenge[4:]
        proof = auth_proof(code or self.identity.pairing_code, nonce, "client")
        writer.write(pack_packet(PKT_HANDSHAKE, 0, proof))
        await writer.drain()
        response = await self.packet(reader)
        self.assertEqual(response, (PKT_HANDSHAKE, 0, auth_proof(self.identity.pairing_code, nonce, "server")))
        return proof

    async def until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(.005)
        self.fail("Server state did not converge")

    async def test_no_event_before_authentication(self):
        reader, writer = await self.connect()
        await self.packet(reader)
        writer.write(pack_events([EVENT]))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.tablet.events, [])

    async def test_bad_credentials_and_replay_rejected(self):
        first = await self.connect()
        proof = await self.authenticate(first)
        first[1].close()
        await self.until(lambda: self.tablet.resets == 1)
        reader, writer = await self.connect()
        await self.packet(reader)
        writer.write(pack_packet(PKT_HANDSHAKE, 0, proof))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.tablet.resets, 1)
        reader, writer = await self.connect()
        _, _, challenge = await self.packet(reader)
        writer.write(pack_packet(PKT_HANDSHAKE, 0, auth_proof("a" * 43, challenge[4:], "client")))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")

    async def test_exclusive_owner_and_eof_release_with_an_idle_peer(self):
        owner = await self.connect()
        await self.authenticate(owner)
        idle = await self.connect()
        await self.packet(idle[0])
        owner[1].write(pack_events([EVENT]))
        await owner[1].drain()
        await self.until(lambda: bool(self.tablet.events))
        owner[1].close()
        await self.until(lambda: self.tablet.resets == 1)
        self.assertFalse(self.server.active_clients)

    async def test_second_authenticated_peer_cannot_inject_or_release_owner(self):
        first = await self.connect()
        await self.authenticate(first)
        second = await self.connect()
        with self.assertRaises(asyncio.IncompleteReadError):
            await self.authenticate(second)
        self.assertEqual(self.tablet.resets, 0)
        first[1].write(pack_events([EVENT]))
        await first[1].drain()
        await self.until(lambda: len(self.tablet.events) == 1)

    async def test_idle_deadline_releases_and_heartbeat_keeps_session_live(self):
        reader, writer = await self.connect()
        await self.authenticate((reader, writer))
        for seq in range(3):
            writer.write(pack_packet(PKT_PING, seq, b""))
            await writer.drain()
            self.assertEqual(await self.packet(reader), (PKT_PONG, seq, b""))
            await asyncio.sleep(.1)
        self.assertTrue(self.server.active_clients)
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.tablet.resets, 1)

    async def test_stop_closes_authenticated_and_unauthenticated_idle_streams(self):
        pair = await self.connect()
        await self.authenticate(pair)
        await self.connect()
        await asyncio.wait_for(self.server.stop(), 1)
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 1), b"")
        self.assertFalse(self.server.active_clients)
        self.assertFalse(self.server._handlers)
        self.assertEqual(self.tablet.resets, 1)

    async def test_device_failure_stops_accepting_and_closes_backend(self):
        pair = await self.connect()
        await self.authenticate(pair)
        self.tablet.handle_event = Mock(side_effect=OSError("device removed"))
        self.tablet.close = Mock()
        pair[1].write(pack_events([EVENT]))
        await pair[1].drain()
        await self.until(lambda: not self.server._handlers)
        self.assertFalse(self.server.is_running)
        self.tablet.close.assert_called_once()

    async def test_failed_neutral_report_closes_backend_and_listener(self):
        pair = await self.connect()
        await self.authenticate(pair)
        self.tablet.reset = Mock(side_effect=OSError("release failed"))
        self.tablet.close = Mock()
        pair[1].close()
        await self.until(lambda: not self.server._handlers)
        self.assertFalse(self.server.is_running)
        self.tablet.close.assert_called_once()

    async def test_rate_limit_releases_without_applying_over_budget_batch(self):
        self.server.event_rate = 1
        pair = await self.connect()
        await self.authenticate(pair)
        pair[1].write(pack_events([EVENT] * 3))
        await pair[1].drain()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 1), b"")
        self.assertEqual(self.tablet.events, [])
        self.assertEqual(self.tablet.resets, 1)

    async def test_authentication_deadline_does_not_reset_another_owners_state(self):
        reader, _ = await self.connect()
        await self.packet(reader)
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        await self.until(lambda: not self.server._writers)
        self.assertFalse(self.server._writers)
        self.assertEqual(self.tablet.resets, 0)

    async def test_application_admission_cap_rejects_an_extra_pending_peer(self):
        self.server.handshake_timeout = 2
        for _ in range(self.server.max_connections):
            pair = await self.connect()
            await self.packet(pair[0])
        with self.assertRaises((ConnectionError, OSError)):
            await self.connect()
        self.assertEqual(self.tablet.events, [])

    async def test_raw_tls_admission_and_shutdown_are_bounded(self):
        raw = []
        try:
            self.server.handshake_timeout = 10
            for _ in range(self.server.max_connections):
                pair = await asyncio.open_connection("127.0.0.1", self.port)
                raw.append(pair)
            await self.until(lambda: len(self.server._connections) == self.server.max_connections)
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            raw.append((reader, writer))
            self.assertEqual(await asyncio.wait_for(reader.read(1), 1), b"")
            self.assertEqual(len(self.server._handlers), self.server.max_connections)
            await asyncio.wait_for(self.server.stop(), 1)
            self.assertFalse(self.server._handlers)
            self.assertFalse(self.server._connections)
        finally:
            for _, writer in raw:
                writer.close()
                await writer.wait_closed()

    async def test_invalid_complete_packet_releases_held_owner(self):
        pair = await self.connect()
        await self.authenticate(pair)
        pair[1].write(pack_events([EVENT]))
        await pair[1].drain()
        await self.until(lambda: len(self.tablet.events) == 1)
        malformed = EVENT_STRUCT.pack(3, 0, 0, .5, .5, math.nan, 0, 0)
        pair[1].write(pack_packet(PKT_EVENT, 1, malformed))
        await pair[1].drain()
        self.assertEqual(await asyncio.wait_for(pair[0].read(), 1), b"")
        self.assertEqual(len(self.tablet.events), 1)
        self.assertEqual(self.tablet.resets, 1)

    async def test_synthetic_tool_uses_paired_tls_and_all_samples_arrive(self):
        from server.test_synthetic import run_synthetic_network_test
        self.server.idle_timeout = 2
        with patch("server.test_synthetic.load_identity", return_value=self.identity):
            await asyncio.to_thread(run_synthetic_network_test, "127.0.0.1", self.port, 1)
        await self.until(lambda: self.tablet.resets == 1)
        self.assertEqual(len(self.tablet.events), 153)
        self.assertEqual(self.tablet.events[-1].action, ACTION_HOVER_EXIT)

    async def test_untrusted_certificate_is_not_accepted(self):
        with self.assertRaises(ssl.SSLError):
            await asyncio.open_connection("127.0.0.1", self.port, ssl=ssl.create_default_context(),
                                          server_hostname="localhost")


class IdentityTests(unittest.TestCase):
    def test_identity_stable_private_and_invalid_identity_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = load_identity(directory)
            again = load_identity(directory)
            self.assertEqual(identity.fingerprint, again.fingerprint)
            self.assertEqual(identity.pairing_code, again.pairing_code)
            self.assertNotIn(identity.pairing_code, repr(identity))
            path = Path(directory) / "identity.json"
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text('{"version": 99}')
            with self.assertRaises(ValueError):
                load_identity(directory)
            self.assertEqual(path.read_text(), '{"version": 99}')


class WorkerOwnershipTests(unittest.TestCase):
    def test_validation_error_callback_can_read_worker_state(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        from server.gui.server_worker import ServerWorker
        config = TabletConfig()
        config.port = 0
        worker = ServerWorker(config)
        observed = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            def callback(status, message):
                if status == "error":
                    request = pool.submit(lambda: worker.state)
                    try:
                        observed.append(request.result(timeout=.5))
                    except TimeoutError:
                        observed.append("blocked by emitting thread")
            worker.sig_status.connect(callback)
            with patch("server.gui.server_worker.create_tablet_backend") as device:
                worker.start_server()
                worker.shutdown()
                device.assert_not_called()
        self.assertEqual(observed, ["stopped"])

    def test_gui_handoff_is_bounded_and_emits_only_one_pending_notification(self):
        from server.gui.server_worker import ServerWorker
        worker = ServerWorker(TabletConfig())
        notifications = []
        worker.sig_pen_events_ready.connect(lambda: notifications.append(True))
        for _ in range(5000):
            worker._on_tablet_event(EVENT, 2000, 100, 100)
        self.assertEqual(len(notifications), 1)
        events = worker.drain_pen_events()
        self.assertLessEqual(len(events), 2048)
        self.assertEqual(events[0][0].action, ACTION_CANCEL)
        self.assertEqual(events[-1][0], EVENT)
        worker._on_tablet_event(EVENT, 2000, 100, 100)
        self.assertEqual(len(notifications), 2)

    def test_double_start_and_stop_during_initialization_release_on_owner_thread(self):
        from server.gui.server_worker import ServerWorker
        entered, proceed = threading.Event(), threading.Event()
        calls = []

        class Tablet(MemoryTablet):
            def close(self):
                calls.append(("close", threading.get_ident()))

        def create(**kwargs):
            calls.append(("create", threading.get_ident()))
            entered.set()
            self.assertTrue(proceed.wait(2))
            return Tablet()

        worker = ServerWorker(TabletConfig())
        with patch("server.gui.server_worker.create_tablet_backend", side_effect=create) as factory:
            worker.start_server()
            self.assertTrue(entered.wait(2))
            worker.start_server()
            worker.stop_server()
            proceed.set()
            worker.shutdown()
            factory.assert_called_once()
        self.assertEqual(worker.state, "stopped")
        self.assertEqual([name for name, _ in calls], ["create", "close"])
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertNotEqual(calls[0][1], threading.get_ident())

    def test_live_settings_and_device_swap_are_serialized_on_owner_thread(self):
        from server.gui.server_worker import ServerWorker
        config = TabletConfig(port=40139)
        operations = []

        class Tablet(MemoryTablet):
            def _setup_device(self):
                super()._setup_device()
                operations.append(("create", threading.get_ident()))

            def update_settings(self, **kwargs):
                operations.append(("update", threading.get_ident()))
                super().update_settings(**kwargs)

            def close(self):
                operations.append(("close", threading.get_ident()))

        class Server:
            def __init__(self, tablet, **kwargs):
                self.tablet = tablet

            async def start(self):
                pass

            async def stop(self):
                operations.append(("stop", threading.get_ident()))

        identity = Mock()
        identity.pairing_code = "a" * 43
        worker = ServerWorker(config)
        with patch("server.gui.server_worker.create_tablet_backend", side_effect=lambda **kw: Tablet(**kw)), \
             patch("server.gui.server_worker.load_identity", return_value=identity), \
             patch("server.gui.server_worker.SPenServer", Server):
            try:
                worker.start_server()
                for _ in range(200):
                    if worker.state == "running":
                        break
                    time.sleep(.005)
                self.assertEqual(worker.state, "running")
                worker.update_tablet_settings(pressure_gamma=2)
                worker.set_device_mode(mode="tablet")
                for _ in range(200):
                    if worker.tablet is not None and worker.tablet.mode == "tablet":
                        break
                    time.sleep(.005)
            finally:
                worker.shutdown()
        self.assertEqual(sum(name == "create" for name, _ in operations), 1 if sys.platform == "win32" else 2)
        self.assertTrue(any(name == "update" for name, _ in operations))
        self.assertEqual(len({owner for _, owner in operations}), 1)
        self.assertNotEqual(operations[0][1], threading.get_ident())


class GuiPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from server.gui.main_window import MainWindow
        config = TabletConfig(auto_start_server=False, minimize_to_tray=False)
        patches = (
            patch("server.gui.main_window.load_config", return_value=config),
            patch("server.gui.main_window.WindowWatcher.start"),
            patch("server.gui.main_window.GuiState", return_value=Mock(last_tab_index=0, last_editing_profile="Default")),
            patch("server.gui.main_window.QMessageBox.information"),
            patch("server.gui.main_window.QMessageBox.warning"),
        )
        for patched in patches:
            patched.start()
            self.addCleanup(patched.stop)
        self.window = MainWindow()
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.window._dirty = False
        self.window.diag_timer.stop()
        self.window.worker.shutdown()
        self.window.system_tab.connection_panel.stop_usb_monitor()
        self.window.hide()
        self.window.deleteLater()

    def test_system_and_active_profile_changes_mark_dirty(self):
        self.assertFalse(self.window._dirty)
        panel = self.window.system_tab.startup_panel
        panel.chk_tray.setChecked(not panel.chk_tray.isChecked())
        self.assertTrue(self.window._dirty)
        self.window._dirty = False
        self.window.set_active_profile("osu!")
        self.assertTrue(self.window._dirty)

    def test_automatic_focus_changes_are_runtime_state_not_unsaved_edits(self):
        self.window._check_active_window("krita", "Drawing")
        self.assertEqual(self.window.config.active_profile_name, "Krita")
        self.assertFalse(self.window._dirty)

    def test_external_label_values_are_plain_text(self):
        from PySide6.QtCore import Qt
        from server.gui.profile_list_panel import ProfileListRow
        from server.gui.widgets.chip_input import MatchChip
        row = ProfileListRow("<b>profile</b>")
        chip = MatchChip("<b>rule</b>")
        self.addCleanup(row.deleteLater)
        self.addCleanup(chip.deleteLater)
        self.assertEqual(row._lbl_name.textFormat(), Qt.PlainText)
        self.assertEqual(chip._label.textFormat(), Qt.PlainText)
        self.assertIn("rule", chip._btn_remove.accessibleName())

    def test_editor_displays_the_full_validated_range_without_clamping_saved_values(self):
        profile = self.window.config.get_active_profile()
        profile.custom_bounds = [-1920, -1080, 20000, 1]
        profile.pressure_gamma = 5
        profile.pressure_min = .49
        profile.pressure_max = .51
        profile.stroke_smoothing = .9
        editor = self.window.profiles_tab.editor_panel
        editor.bind_profile(profile)
        mapping = editor.mapping_section
        self.assertEqual([widget.value() for widget in (mapping.spin_cust_x, mapping.spin_cust_y,
                                                        mapping.spin_cust_w, mapping.spin_cust_h)], profile.custom_bounds)
        self.assertEqual(editor.pressure_section.slider_gamma.value(), 500)
        self.assertEqual(editor.pressure_section.slider_min.value(), 49)
        self.assertEqual(editor.pressure_section.slider_max.value(), 51)
        self.assertEqual(editor.buttons_section.slider_smooth.value(), 90)
        self.window.config.port = 80
        self.window.system_tab.startup_panel._sync_from_config()
        self.assertEqual(self.window.system_tab.startup_panel.spin_port.value(), 80)

    def test_connection_details_remain_on_running_port_until_restart(self):
        panel = self.window.system_tab.connection_panel
        self.addCleanup(panel.stop_usb_monitor)
        panel.set_listener(("127.0.0.1", 40118))
        self.window.system_tab.startup_panel.spin_port.setValue(41234)
        self.assertEqual(panel.address(), "127.0.0.1:40118")
        self.assertIn("pending", panel.lbl_hint.text())
        panel._copy_connection_info()
        self.assertEqual(self.app.clipboard().text(), "127.0.0.1:40118")
        with patch("server.gui.connection_panel.subprocess.run", return_value=Mock(returncode=0)) as run:
            panel.run_adb_reverse(silent=True)
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertEqual(run.call_args.args[0], ["adb", "-d", "reverse", "tcp:40118", "tcp:40118"])
        panel.set_listener(None)
        self.assertEqual(panel.address(), "127.0.0.1:41234")

    def test_adb_waits_for_the_startup_snapshot_endpoint(self):
        panel = self.window.system_tab.connection_panel
        self.addCleanup(panel.stop_usb_monitor)
        panel.set_transitioning()
        self.window.config.port = 41234  # Edited after the worker took its snapshot.
        with patch("server.gui.connection_panel.subprocess.run", return_value=Mock(returncode=0)) as run:
            panel.run_adb_reverse(silent=True)
            run.assert_not_called()
            self.assertFalse(panel.btn_copy.isEnabled())
            panel.set_listener(("127.0.0.1", 40118))
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertEqual(run.call_args.args[0], ["adb", "-d", "reverse", "tcp:40118", "tcp:40118"])
            self.assertTrue(panel.btn_copy.isEnabled())

    def test_usb_monitor_has_one_bounded_job_and_stops_cleanly(self):
        panel = self.window.system_tab.connection_panel
        self.addCleanup(panel.stop_usb_monitor)
        started, release = threading.Event(), threading.Event()
        def blocked(*args, **kwargs):
            started.set()
            release.wait(2)
            return Mock(returncode=0)
        with patch("server.gui.connection_panel.subprocess.run", side_effect=blocked) as run:
            panel.run_adb_reverse(silent=True)
            try:
                self.assertTrue(started.wait(1))
                original = panel._adb_thread
                for _ in range(5):
                    panel.run_adb_reverse(silent=True, automatic=True)
                self.assertIs(panel._adb_thread, original)
                self.assertEqual(run.call_count, 1)
            finally:
                release.set()
                panel.stop_usb_monitor()
                self.app.processEvents()
            self.assertFalse(panel._usb_timer.isActive())
            self.assertFalse(original.is_alive())

    def test_usb_forward_restores_after_replug_without_replacing_a_live_forward(self):
        panel = self.window.system_tab.connection_panel
        self.addCleanup(panel.stop_usb_monitor)
        panel.set_listener(("127.0.0.1", 40118))
        ready = Mock(returncode=0, stdout="UsbFfs tcp:40118 tcp:40118\n")
        missing = Mock(returncode=0, stdout="")
        offline = Mock(returncode=1, stdout="")
        with patch("server.gui.connection_panel.subprocess.run", return_value=ready) as run:
            panel.run_adb_reverse(silent=True)
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertTrue(panel._usb_timer.isActive())
            panel.set_client("127.0.0.1:12345")
            self.assertEqual(panel.connection_type(), "USB (ADB)")
            run.reset_mock()
            panel.run_adb_reverse(silent=True, automatic=True)
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertEqual([call.args[0] for call in run.call_args_list], [["adb", "-d", "reverse", "--list"]])
            panel.set_client(None)
            run.return_value = offline
            panel.run_adb_reverse(silent=True, automatic=True)
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertFalse(panel._usb_ready)
            self.assertIn("waiting for device", panel.lbl_transport.text())
            run.reset_mock()
            run.side_effect = [missing, ready]
            panel.run_adb_reverse(silent=True, automatic=True)
            panel._adb_thread.join(2)
            self.app.processEvents()
            self.assertEqual([call.args[0] for call in run.call_args_list], [
                ["adb", "-d", "reverse", "--list"], ["adb", "-d", "reverse", "tcp:40118", "tcp:40118"]])
            self.assertTrue(panel._usb_ready)
            panel.set_client("127.0.0.1:23456")
            self.assertIn("USB", panel.lbl_transport.text())
            self.window.on_client_connected("127.0.0.1:23456")
            self.assertIn("USB", self.window.header_bar.status_badge.text())
            self.window.on_client_connected("192.168.1.3:23456")
            self.assertIn("Wi-Fi", self.window.header_bar.status_badge.text())
            panel.set_client("192.168.1.3:23456")
            self.assertEqual(panel.connection_type(), "Wi-Fi / network")
        panel.stop_usb_monitor()
        self.assertFalse(panel._usb_timer.isActive())

    def test_collapsible_header_and_monitor_map_support_keyboard(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from server.gui.widgets.collapsible_box import CollapsibleBox
        from server.widgets.monitor_layout import MonitorLayoutWidget
        box = CollapsibleBox("Advanced settings")
        self.addCleanup(box.deleteLater)
        QTest.keyClick(box._header, Qt.Key_Space)
        self.assertTrue(box.is_expanded)
        self.assertTrue(box._header.isChecked())
        self.assertEqual(box._header.accessibleName(), "Advanced settings")
        # AT-SPI exposes this checkable button as a checkbox. Its Toggle
        # action changes checked state directly, without a clicked signal.
        changes = []
        box.toggled_expanded.connect(changes.append)
        box._header.toggle()
        self.assertFalse(box.is_expanded)
        self.assertFalse(box._body.isVisibleTo(box))
        box._header.toggle()
        self.assertTrue(box.is_expanded)
        self.assertTrue(box._body.isVisibleTo(box))
        self.assertEqual(changes, [False, True])
        panel = self.window.profiles_tab.list_panel
        self.assertEqual(panel.list_widget.accessibleName(), "Profiles")
        for name, item in panel._items.items():
            self.assertEqual(item.data(Qt.AccessibleTextRole), name)
        monitor = MonitorLayoutWidget()
        self.addCleanup(monitor.deleteLater)
        monitors = [dict(name="A", x=0, y=0, width=100, height=100),
                    dict(name="B", x=100, y=0, width=100, height=100)]
        monitor.set_data(monitors, (200, 100), "all", "")
        chosen = []
        monitor.monitor_clicked.connect(chosen.append)
        QTest.keyClick(monitor, Qt.Key_Right)
        QTest.keyClick(monitor, Qt.Key_Return)
        self.assertEqual(chosen, ["B"])

    def test_button_choices_follow_backend_capabilities_without_silent_remapping(self):
        from server.button_actions import available_actions
        editor = self.window.profiles_tab.editor_panel
        profile = self.window.config.get_active_profile()
        profile.device_mode = "pointer"
        profile.button_secondary = "stylus2"
        editor.bind_profile(profile)
        combo = editor.buttons_section.combo_btn_sec
        self.assertEqual(combo.currentData(), "stylus2")
        allowed = available_actions(sys.platform, "pointer")
        for i in range(combo.count()):
            self.assertEqual(combo.model().item(i).isEnabled(), combo.itemData(i) in allowed)
        self.assertEqual(profile.button_secondary, "stylus2")

    def test_failed_save_prevents_close_and_tray_quit(self):
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox
        self.window._dirty = True
        with patch("server.gui.main_window.QMessageBox.question", return_value=QMessageBox.Save), \
             patch("server.gui.main_window.save_config", return_value=False), \
             patch("server.gui.main_window.QApplication.quit") as quit_app:
            event = QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertFalse(self.window.force_quit())
            quit_app.assert_not_called()
        self.assertTrue(self.window._dirty)

    def test_reset_rebinds_global_controls_and_failed_reset_preserves_config(self):
        from PySide6.QtWidgets import QMessageBox
        mapping = self.window.profiles_tab.editor_panel.mapping_section
        mapping.chk_aspect_lock.setChecked(True)
        self.window.profiles_tab.list_panel.chk_auto_switch.setChecked(False)
        previous = self.window.config
        with patch("server.gui.main_window.QMessageBox.question", return_value=QMessageBox.Yes), \
             patch("server.gui.main_window.save_config", return_value=False):
            self.window._reset_defaults()
        self.assertIs(self.window.config, previous)
        with patch("server.gui.main_window.QMessageBox.question", return_value=QMessageBox.Yes), \
             patch("server.gui.main_window.save_config", return_value=True):
            self.window._reset_defaults()
        self.assertFalse(mapping.chk_aspect_lock.isChecked())
        self.assertTrue(self.window.profiles_tab.list_panel.chk_auto_switch.isChecked())
        self.assertEqual(self.window.header_bar.lbl_active_mode_prefix.text(), "Auto:")
        self.assertFalse(self.window._dirty)

    def test_preview_preserves_stroke_boundaries_and_never_replays_a_cached_sample(self):
        self.window.tabs.setCurrentIndex(1)
        scratch = self.window.system_tab.scratchpad_panel.scratchpad
        actions = [ACTION_DOWN, ACTION_MOVE, ACTION_UP, ACTION_DOWN, ACTION_UP]
        with patch.object(scratch, "add_tablet_points") as draw:
            for action in actions:
                self.window.on_pen_event(replace(EVENT, action=action), 2000, 100, 100)
            self.window.update_live_diagnostics()
            self.assertEqual([p[3] for p in draw.call_args.args[0]], actions)
            self.window.update_live_diagnostics()
            draw.assert_called_once()

    def test_disconnect_clears_pressure_and_eraser_diagnostics(self):
        diagnostics = self.window.system_tab.diagnostics_panel
        self.window.on_pen_event(replace(EVENT, tool_type=1), 2000, 100, 100)
        self.window.update_live_diagnostics()
        self.assertEqual(diagnostics.badge_eraser.property("pillState"), "ok")
        self.window.on_client_disconnected("test")
        self.assertEqual(diagnostics.bar_pressure.value(), 0)
        self.assertEqual(diagnostics.badge_eraser.property("pillState"), "idle")
        self.assertFalse(self.window._preview_events)

    def test_plain_text_logs_are_bounded(self):
        logs = self.window.system_tab.log_panel
        logs.log("<b>literal title</b>")
        self.assertIn("<b>literal title</b>", logs.text_logs.toPlainText())
        for _ in range(1050):
            logs.log("sample")
        self.assertLessEqual(logs.text_logs.document().blockCount(), 1001)
        self.assertNotIn("literal title", logs.text_logs.toPlainText())

    def test_quit_cancels_pending_automatic_starts(self):
        operation = Mock()
        self.window._schedule_startup(100, operation)
        self.assertTrue(self.window._startup_timers[0].isActive())
        with patch("server.gui.main_window.QApplication.quit"):
            self.assertTrue(self.window.force_quit(discard_confirmed=True))
        self.assertFalse(self.window._startup_timers)
        operation.assert_not_called()
