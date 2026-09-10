"""Windows HID contract and state transitions, runnable without a driver."""
import math
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from server.backends.windows_hid import WindowsHidTablet
from server.backends.windows_report import (
    PEN_REPORT, IOCTL_SUBMIT_REPORT, TIP, BARREL, IN_RANGE, INVERT, ERASER,
    pack_pen, pack_mouse,
)
from server.protocol import PenEvent


class ReportTests(unittest.TestCase):
    def test_wire_bytes_and_clamping(self):
        self.assertEqual(pack_pen(31, 0x1234, 32767, 1000, -90, 90),
                         b'\x01\x1f\x34\x12\xff\x7f\xe8\x03\xa6\x5a')
        self.assertEqual(PEN_REPORT.unpack(pack_pen(255, -1, 99999, -1, -100, 100)),
                         (1, 31, 0, 32767, 0, -90, 90))
        self.assertEqual(pack_mouse(7), b'\x02\x07\x00\x00')
        self.assertEqual(IOCTL_SUBMIT_REPORT, 0x22A000)

    def test_descriptor_report_lengths_match_python(self):
        source = (Path(__file__).resolve().parents[1] /
                  'windows/driver/spenvhid/report_descriptor.h').read_text()
        source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
        data = bytes(int(v, 16) for v in re.findall(r'0x([0-9A-Fa-f]{2})', source))
        size = count = report_id = 0
        bits = {}
        offset = 0
        while offset < len(data):
            prefix = data[offset]
            length = (0, 1, 2, 4)[prefix & 3]
            value = int.from_bytes(data[offset+1:offset+1+length], 'little')
            tag = prefix & 0xFC
            if tag == 0x74: size = value
            if tag == 0x94: count = value
            if tag == 0x84: report_id = value
            if tag == 0x80: bits[report_id] = bits.get(report_id, 0) + size * count
            offset += 1 + length
        self.assertEqual(bits, {1: 72, 2: 24})


class BackendTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('server.backends.windows_hid.DriverConnection')
        self.connection = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.tablet = WindowsHidTablet()
        self.addCleanup(self.tablet.close)

    def event(self, action, **kwargs):
        fields = dict(action=action, tool_type=0, buttons=0, x=.5, y=.5, pressure=.5)
        fields.update(kwargs)
        self.tablet.handle_event(PenEvent(**fields))

    def last_pen(self):
        reports = [c.args[0] for c in self.connection.submit.call_args_list if c.args[0][0] == 1]
        return PEN_REPORT.unpack(reports[-1])

    def test_down_hover_up_and_exit(self):
        self.event(3, tilt_x=-45, tilt_y=20)
        self.assertEqual(self.last_pen(), (1, TIP | IN_RANGE, 16383, 16383, 16383, -45, 20))
        for action in (0, 1, 5):
            self.event(action, pressure=1)
            self.assertEqual(self.last_pen()[1], IN_RANGE)
            self.assertEqual(self.last_pen()[4], 0)
        self.event(2)
        self.assertEqual(self.last_pen()[1], 0)

    def test_eraser_and_buttons_release_on_cancel(self):
        self.event(3, tool_type=1, buttons=3)
        self.assertEqual(self.last_pen()[1], IN_RANGE | INVERT | ERASER | BARREL)
        self.connection.submit.assert_called_with(pack_mouse(4))
        self.event(6)
        self.assertEqual(self.last_pen()[1], 0)
        self.connection.submit.assert_called_with(pack_mouse())

    def test_smoothing_only_strokes_and_monitor_mapping(self):
        self.tablet.update_settings(stroke_smoothing=.5, screen_bounds=(100, 0, 100, 100),
                                    desktop_size=(200, 100))
        self.event(3, x=0)
        self.event(4, x=1)
        self.assertEqual(self.last_pen()[2], int(.75 * 32767))
        self.event(0, x=1)
        self.assertEqual(self.last_pen()[2], 32767)

    def test_click_disable_releases_immediately(self):
        self.event(3)
        self.tablet.update_settings(click_on_touch=False)
        self.assertEqual(self.last_pen()[1] & TIP, 0)
        self.assertEqual(self.last_pen()[4], 0)
        self.event(4)
        self.assertEqual(self.last_pen()[1] & TIP, 0)

    def test_remapping_releases_held_buttons(self):
        self.event(0, buttons=2)
        self.tablet.update_settings(button_secondary='left_click')
        self.connection.submit.assert_called_with(pack_mouse())
        self.event(0, buttons=2)
        self.connection.submit.assert_called_with(pack_mouse(1))

    def test_invalid_input_ignored(self):
        for value in (math.nan, math.inf, -math.inf):
            self.event(3, pressure=value)
        self.event(3, tool_type=2)
        self.event(99)
        self.connection.submit.assert_not_called()

    def test_close_idempotent_even_when_device_disappears(self):
        self.connection.submit.side_effect = OSError('removed')
        self.tablet.close()
        self.tablet.close()
        self.connection.close.assert_called_once()

    def test_driver_errors_propagate(self):
        self.connection.submit.side_effect = OSError('driver unavailable')
        with self.assertRaises(OSError):
            self.event(3)
        self.connection.submit.side_effect = None


class DisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_eof_releases_pen_and_buttons(self):
        from unittest.mock import AsyncMock, Mock
        from server.server import SPenServer
        from server.protocol import pack_events
        with patch('server.backends.windows_hid.DriverConnection') as transport:
            tablet = WindowsHidTablet()
            reader = AsyncMock()
            reader.read.side_effect = [pack_events([PenEvent(3, 0, 3, .5, .5, .7)]), b'']
            writer = Mock()
            writer.get_extra_info.return_value = None
            writer.wait_closed = AsyncMock()
            server = SPenServer(tablet)
            server._running = True
            await server._handle_client(reader, writer)
            self.assertFalse(tablet._is_down)
            reports = [call.args[0] for call in transport.return_value.submit.call_args_list]
            self.assertGreater(len(reports), 2)
            self.assertEqual(PEN_REPORT.unpack(reports[-2])[1], 0)
            self.assertEqual(reports[-1], pack_mouse())
            tablet.close()


class WindowsIntegrationTests(unittest.TestCase):
    def test_negative_monitor_origin_and_small_desktop(self):
        from server.monitors import detect_monitors
        monitors = [dict(name='left', x=-1280, y=-100, width=1280, height=720),
                    dict(name='main', x=0, y=0, width=1280, height=720)]
        with patch('server.monitors.get_monitors_from_qt', return_value=monitors), \
             patch('server.monitors.sys.platform', 'win32'):
            mapped, desktop = detect_monitors()
        self.assertEqual(desktop, (2560, 820))
        self.assertEqual((mapped[0]['x'], mapped[0]['y']), (0, 0))
        self.assertEqual((mapped[1]['x'], mapped[1]['y']), (1280, 100))
        self.assertEqual(monitors[0]['x'], -1280)

    def test_windows_profile_mode_switch_keeps_exclusive_connection(self):
        from server.config import TabletConfig
        from server.gui.server_worker import ServerWorker
        with patch('server.backends.windows_hid.DriverConnection') as connection:
            tablet = WindowsHidTablet()
            worker = ServerWorker(TabletConfig())
            worker.tablet = tablet
            with patch('server.gui.server_worker.sys.platform', 'win32'), \
                 patch('server.gui.server_worker.create_tablet_backend') as factory:
                worker.set_device_mode(mode='tablet', device_name='Drawing')
            factory.assert_not_called()
            self.assertIs(worker.tablet, tablet)
            self.assertEqual(tablet.name, 'Drawing')
            connection.assert_called_once()
            tablet.close()
