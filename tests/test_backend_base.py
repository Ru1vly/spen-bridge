"""
Tests for TabletBackendBase's OS-agnostic pure math (server.backends.base),
independent of any concrete backend. Confirms COORD_MAX/PRESSURE_MAX are
genuine per-subclass override points - the mechanism WindowsHidTablet will
rely on to target the Windows HID descriptor's 0..32767 logical range while
LinuxUinputTablet keeps the historical uinput ABS_MAX_* defaults unchanged.
"""

import unittest

from server.backends.base import ABS_MAX_COORDINATE, ABS_MAX_PRESSURE, TabletBackendBase


class _FakeBackend(TabletBackendBase):
    """Minimal concrete subclass: no real device I/O, just the pure math."""

    def _setup_device(self):
        pass

    def handle_event(self, ev):
        pass

    def _release_touch(self):
        pass

    def close(self):
        pass


class _OverriddenRangeBackend(_FakeBackend):
    COORD_MAX = 32767
    PRESSURE_MAX = 32767


class TestTabletBackendBaseRanges(unittest.TestCase):
    def test_default_ranges_match_linux_constants(self):
        backend = _FakeBackend()
        self.assertEqual(backend.COORD_MAX, ABS_MAX_COORDINATE)
        self.assertEqual(backend.PRESSURE_MAX, ABS_MAX_PRESSURE)
        self.assertEqual(backend.calibrate_pressure(1.0), ABS_MAX_PRESSURE)
        self.assertEqual(backend._map_coordinates(1.0, 1.0), (ABS_MAX_COORDINATE, ABS_MAX_COORDINATE))

    def test_subclass_overriding_coord_max_scales_map_coordinates(self):
        backend = _OverriddenRangeBackend()
        self.assertEqual(backend._map_coordinates(0.0, 0.0), (0, 0))
        self.assertEqual(backend._map_coordinates(1.0, 1.0), (32767, 32767))
        self.assertEqual(backend._map_coordinates(0.5, 0.5), (16383, 16383))

    def test_subclass_overriding_coord_max_scales_screen_bounds_mapping(self):
        backend = _OverriddenRangeBackend()
        backend.screen_bounds = (0, 0, 1000, 500)
        backend.desktop_size = (1000, 500)
        self.assertEqual(backend._map_coordinates(1.0, 1.0), (32767, 32767))

    def test_subclass_overriding_pressure_max_scales_calibrate_pressure(self):
        backend = _OverriddenRangeBackend()
        self.assertEqual(backend.calibrate_pressure(0.0), 0)
        self.assertEqual(backend.calibrate_pressure(1.0), 32767)

    def test_multi_monitor_normalization_and_mapping(self):
        from server.monitors import detect_monitors
        from unittest.mock import patch
        raw_monitors = [
            {"name": "HDMI-1", "x": -1920, "y": 0, "width": 1920, "height": 1080, "primary": False},
            {"name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True},
        ]
        with patch("server.monitors.get_monitors_from_qt", return_value=raw_monitors):
            monitors, (desk_w, desk_h) = detect_monitors()
            self.assertEqual((desk_w, desk_h), (3840, 1080))
            self.assertEqual((monitors[0]["x"], monitors[0]["y"]), (0, 0))
            self.assertEqual((monitors[1]["x"], monitors[1]["y"]), (1920, 0))

        # Check that backend maps properly to the left screen
        backend = _FakeBackend()
        backend.screen_bounds = (monitors[0]["x"], monitors[0]["y"], monitors[0]["width"], monitors[0]["height"])
        backend.desktop_size = (desk_w, desk_h)
        # Left edge of left monitor maps to 0
        self.assertEqual(backend._map_coordinates(0.0, 0.0), (0, 0))
        # Right edge of left monitor maps to exactly half of ABS_MAX_COORDINATE
        x_mapped, _ = backend._map_coordinates(1.0, 0.0)
        self.assertAlmostEqual(x_mapped / ABS_MAX_COORDINATE, 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
