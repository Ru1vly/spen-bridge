"""
Tests for the Linux uinput tablet backend. These construct a real
LinuxUinputTablet (which opens /dev/uinput) or import evdev.ecodes directly,
so they're skipped everywhere except Linux - see server/backends/ for the
cross-platform seam these tests exercise the Linux side of.
"""

import os
import sys
import unittest

# Ensure headless execution works in CI/headless environments without X11/Wayland
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for Qt widgets
app = QApplication.instance() or QApplication(sys.argv)

from server.config import TabletConfig


try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

@unittest.skipUnless(sys.platform.startswith("linux") and os.access("/dev/uinput", os.W_OK) and HAS_EVDEV,
                     "requires writable /dev/uinput and evdev module")
class TestLinuxUinputBackend(unittest.TestCase):
    def test_pressure_calibration_curves(self):
        from server.backends.linux_uinput import LinuxUinputTablet, ABS_MAX_PRESSURE

        # Create virtual tablet in pointer mode
        vt = LinuxUinputTablet(
            pressure_curve_type="linear",
            pressure_gamma=1.0,
            pressure_min=0.0,
            pressure_max=1.0,
        )

        # 1. Linear curve
        self.assertEqual(vt.calibrate_pressure(0.0), 0)
        self.assertEqual(vt.calibrate_pressure(1.0), ABS_MAX_PRESSURE)
        mid_p = vt.calibrate_pressure(0.5)
        self.assertAlmostEqual(mid_p / ABS_MAX_PRESSURE, 0.5, delta=0.05)

        # 2. Deadzone test
        vt.update_settings(pressure_min=0.1, pressure_max=0.9)
        self.assertEqual(vt.calibrate_pressure(0.05), 0)  # below deadzone
        self.assertEqual(vt.calibrate_pressure(0.95), ABS_MAX_PRESSURE)  # above ceiling
        self.assertAlmostEqual(vt.calibrate_pressure(0.5) / ABS_MAX_PRESSURE, 0.5, delta=0.05)

        # 3. Soft curve (reaches higher pressure sooner)
        vt.update_settings(pressure_curve_type="soft", pressure_min=0.0, pressure_max=1.0)
        p_soft = vt.calibrate_pressure(0.5)
        self.assertGreater(p_soft, mid_p)

        # 4. Firm curve (requires higher pressure)
        vt.update_settings(pressure_curve_type="firm")
        p_firm = vt.calibrate_pressure(0.5)
        self.assertLess(p_firm, mid_p)

        vt.close()

    def test_hover_tracks_pen_during_smoothing(self):
        """Regression test: with stroke smoothing enabled (e.g. Krita's default
        profile, smoothing=0.15), hovering (not touching) must track the pen
        1:1. Previously HOVER_ENTER/HOVER_MOVE matched none of the smoothing
        branches, so the reported cursor position froze at wherever the last
        stroke ended and never followed the pen while it was only hovering:
        it would only "catch up" the instant the pen touched down again."""
        from server.backends.linux_uinput import LinuxUinputTablet
        from server.protocol import PenEvent, ACTION_DOWN, ACTION_UP, ACTION_HOVER_ENTER, ACTION_HOVER_MOVE, TOOL_STYLUS

        vt = LinuxUinputTablet(stroke_smoothing=0.15, mode="pointer")
        vt.uinput.write = lambda type_, code, val: None
        try:
            vt.handle_event(PenEvent(ACTION_DOWN, TOOL_STYLUS, 0, 0.5, 0.5, 0.5))
            vt.handle_event(PenEvent(ACTION_UP, TOOL_STYLUS, 0, 0.5, 0.5, 0.0))
            vt.handle_event(PenEvent(ACTION_HOVER_ENTER, TOOL_STYLUS, 0, 0.5, 0.5, 0.0))

            for y in (0.6, 0.7, 0.8, 0.9, 0.95):
                vt.handle_event(PenEvent(ACTION_HOVER_MOVE, TOOL_STYLUS, 0, 0.5, y, 0.0))
                self.assertAlmostEqual(vt._smooth_y, y, places=6)
        finally:
            vt.close()

    def test_screen_bounds_mapping(self):
        from server.backends.linux_uinput import LinuxUinputTablet, ABS_MAX_COORDINATE

        vt = LinuxUinputTablet(
            screen_bounds=(0, 0, 1920, 1080),
            desktop_size=(1920, 2160),
        )
        x_mid, y_mid = vt._map_coordinates(0.5, 0.5)

        # In top monitor of stacked desktop (1920x2160)
        self.assertAlmostEqual(x_mid / ABS_MAX_COORDINATE, 0.5, places=2)
        self.assertAlmostEqual(y_mid / ABS_MAX_COORDINATE, 0.25, places=2)

        vt.close()

    def test_get_screen_bounds_prefers_freshly_detected_desktop_size(self):
        """Regression test: TabletConfig.desktop_size can go stale (its default
        doesn't match any particular real monitor, and nothing else keeps it in
        sync unless the user manually refreshes). get_screen_bounds_and_desktop()
        must prefer a freshly-detected desktop size when the caller has one,
        instead of always trusting the persisted config value. Otherwise, e.g.,
        selecting a real 1920x1080 monitor in "monitor" mapping mode while
        config.desktop_size still holds a taller stale/default value silently
        caps the pen's vertical reach partway down the screen."""
        from server.backends.linux_uinput import LinuxUinputTablet, ABS_MAX_COORDINATE

        cfg = TabletConfig()
        cfg.mapping_mode = "monitor"
        cfg.selected_monitor = "DP-1"
        monitors = [{"name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True}]

        # Simulate a stale persisted desktop_size that no longer matches the
        # real, freshly-detected single-monitor desktop.
        cfg.desktop_size = [1920, 2160]

        # Without a freshly-detected size, the (buggy, pre-fix) stale value is used.
        sb, desk = cfg.get_screen_bounds_and_desktop(monitors)
        self.assertEqual(desk, (1920, 2160))

        # With one supplied, it must win.
        sb, desk = cfg.get_screen_bounds_and_desktop(monitors, (1920, 1080))
        self.assertEqual(sb, (0, 0, 1920, 1080))
        self.assertEqual(desk, (1920, 1080))

        vt = LinuxUinputTablet(screen_bounds=sb, desktop_size=desk)
        try:
            _, abs_y_bottom = vt._map_coordinates(0.5, 1.0)
            self.assertAlmostEqual(abs_y_bottom / ABS_MAX_COORDINATE, 1.0, places=2)
        finally:
            vt.close()

    def test_click_on_touch_disabled(self):
        from server.backends.linux_uinput import LinuxUinputTablet
        from server.protocol import PenEvent, ACTION_DOWN, TOOL_STYLUS
        import evdev.ecodes as e

        vt = LinuxUinputTablet(click_on_touch=False, mode="pointer")
        written_events = []
        vt.uinput.write = lambda type_, code, val: written_events.append((type_, code, val))

        ev = PenEvent(
            action=ACTION_DOWN,
            tool_type=TOOL_STYLUS,
            buttons=0,
            x=0.5,
            y=0.5,
            pressure=0.8,
            tilt_x=0.0,
            tilt_y=0.0,
        )
        vt.handle_event(ev)

        # In osu! mode (click_on_touch=False), BTN_TOUCH and BTN_LEFT are never emitted
        key_codes = [code for type_, code, val in written_events if type_ == e.EV_KEY]
        self.assertNotIn(e.BTN_TOUCH, key_codes)
        self.assertNotIn(e.BTN_LEFT, key_codes)

        # But absolute cursor coordinates and pressure are emitted
        abs_codes = [code for type_, code, val in written_events if type_ == e.EV_ABS]
        self.assertIn(e.ABS_X, abs_codes)
        self.assertIn(e.ABS_Y, abs_codes)
        self.assertIn(e.ABS_PRESSURE, abs_codes)

        vt.close()

    def test_barrel_button_mapping(self):
        from server.backends.linux_uinput import LinuxUinputTablet
        from server.protocol import PenEvent, ACTION_DOWN, TOOL_STYLUS, BUTTON_STYLUS
        import evdev.ecodes as e

        # 1. Primary button = none
        vt = LinuxUinputTablet(button_primary="none", mode="pointer")
        written = []
        vt.uinput.write = lambda type_, code, val: written.append((type_, code, val))

        ev = PenEvent(
            action=ACTION_DOWN,
            tool_type=TOOL_STYLUS,
            buttons=BUTTON_STYLUS,
            x=0.5,
            y=0.5,
            pressure=0.5,
        )
        vt.handle_event(ev)
        key_codes = [c for t, c, v in written if t == e.EV_KEY]
        self.assertNotIn(e.BTN_RIGHT, key_codes)
        self.assertNotIn(e.BTN_MIDDLE, key_codes)
        vt.close()

        # 2. Primary button = middle_click
        vt2 = LinuxUinputTablet(button_primary="middle_click", mode="pointer")
        written2 = []
        vt2.uinput.write = lambda type_, code, val: written2.append((type_, code, val))
        vt2.handle_event(ev)
        key_codes2 = [c for t, c, v in written2 if t == e.EV_KEY and v == 1]
        self.assertIn(e.BTN_MIDDLE, key_codes2)
        vt2.close()

    def test_device_mode_hotswap(self):
        from server.gui import ServerWorker

        cfg = TabletConfig()
        cfg.port = 40129
        cfg.device_mode = "tablet"
        worker = ServerWorker(cfg)
        worker.start_server()
        try:
            import time
            for _ in range(30):
                if worker.tablet is not None:
                    break
                time.sleep(0.1)
            self.assertIsNotNone(worker.tablet)
            self.assertEqual(worker.tablet.mode, "tablet")

            # Hot-swap to pointer mode
            worker.set_device_mode(mode="pointer")
            self.assertEqual(worker.tablet.mode, "pointer")
            self.assertEqual(worker.server.tablet.mode, "pointer")
        finally:
            worker.stop_server()
            if worker.tablet:
                worker.tablet.close()


if __name__ == "__main__":
    unittest.main()
