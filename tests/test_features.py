import sys
import unittest
import math

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for Qt widgets
app = QApplication.instance() or QApplication(sys.argv)

from server.config import TabletConfig, load_config, save_config
from server.monitors import detect_monitors
from server.virtual_tablet import VirtualTablet, ABS_MAX_PRESSURE, ABS_MAX_COORDINATE
from server.widgets.pressure_curve import PressureCurveWidget


class TestSPenSettingsAndFeatures(unittest.TestCase):
    def test_config_defaults_and_serialization(self):
        cfg = TabletConfig()
        self.assertEqual(cfg.port, 40118)
        self.assertEqual(cfg.pressure_curve_type, "linear")
        self.assertEqual(cfg.pressure_min, 0.0)
        self.assertEqual(cfg.pressure_max, 1.0)
        self.assertEqual(cfg.stroke_smoothing, 0.0)
        self.assertEqual(cfg.button_primary, "right_click")

        d = cfg.to_dict()
        self.assertIn("port", d)
        self.assertIn("pressure_curve_type", d)

        reloaded = TabletConfig.from_dict(d)
        self.assertEqual(reloaded.port, 40118)
        self.assertEqual(reloaded.pressure_curve_type, "linear")

    def test_pressure_calibration_curves(self):
        # Create virtual tablet in pointer mode
        vt = VirtualTablet(
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

    def test_pressure_widget_calculation(self):
        pw = PressureCurveWidget()
        pw.set_params("linear", 1.0, 0.0, 1.0)
        self.assertAlmostEqual(pw.calculate_output(0.5), 0.5, delta=0.01)

        pw.set_params("soft", 1.0, 0.0, 1.0)
        self.assertGreater(pw.calculate_output(0.5), 0.5)

        pw.set_params("firm", 1.0, 0.0, 1.0)
        self.assertLess(pw.calculate_output(0.5), 0.5)

    def test_monitor_detection(self):
        monitors, desk_size = detect_monitors()
        self.assertTrue(len(monitors) >= 1)
        self.assertTrue(desk_size[0] >= 1920)
        self.assertTrue(desk_size[1] >= 1080)
        for m in monitors:
            self.assertIn("name", m)
            self.assertIn("x", m)
            self.assertIn("y", m)
            self.assertIn("width", m)
            self.assertIn("height", m)

    def test_screen_bounds_mapping(self):
        vt = VirtualTablet(
            screen_bounds=(0, 0, 1920, 1080),
            desktop_size=(1920, 2160),
        )
        x_mid, y_mid = vt._map_coordinates(0.5, 0.5)

        # In top monitor of stacked desktop (1920x2160)
        self.assertAlmostEqual(x_mid / ABS_MAX_COORDINATE, 0.5, places=2)
        self.assertAlmostEqual(y_mid / ABS_MAX_COORDINATE, 0.25, places=2)

        vt.close()

    def test_click_on_touch_disabled(self):
        from server.protocol import PenEvent, ACTION_DOWN, TOOL_STYLUS
        import evdev.ecodes as e

        vt = VirtualTablet(click_on_touch=False, mode="pointer")
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

    def test_profile_matching(self):
        cfg = TabletConfig()

        # Test osu! window matching
        p_osu = cfg.find_profile_for_app(app_id="osu!", title="osu!")
        self.assertIsNotNone(p_osu)
        self.assertEqual(p_osu.name, "osu!")
        self.assertFalse(p_osu.click_on_touch)
        self.assertEqual(p_osu.stroke_smoothing, 0.0)

        # Test osu-lazer title matching
        p_lazer = cfg.find_profile_for_app(app_id="osu-lazer", title="osu! (release)")
        self.assertIsNotNone(p_lazer)
        self.assertEqual(p_lazer.name, "osu!")

        # Test Krita match
        p_krita = cfg.find_profile_for_app(app_id="org.kde.krita", title="drawing.kra - Krita")
        self.assertIsNotNone(p_krita)
        self.assertEqual(p_krita.name, "Krita")
        self.assertTrue(p_krita.click_on_touch)

        # Test unmatched window falls back to Default
        p_def = cfg.find_profile_for_app(app_id="firefox", title="Mozilla Firefox")
        self.assertIsNotNone(p_def)
        self.assertEqual(p_def.name, "Default")

    def test_systematic_profile_independence(self):
        """Verify that every feature can be independently enabled/disabled on Default and on App Profiles."""
        cfg = TabletConfig()

        # 1. Default profile modifications
        cfg.active_profile_name = "Default"
        cfg.click_on_touch = False
        cfg.stroke_smoothing = 0.45
        cfg.button_primary = "middle_click"
        cfg.pressure_curve_type = "firm"
        cfg.pressure_gamma = 1.8

        self.assertFalse(cfg.get_active_profile().click_on_touch)
        self.assertEqual(cfg.get_active_profile().stroke_smoothing, 0.45)
        self.assertEqual(cfg.get_active_profile().button_primary, "middle_click")

        # 2. Switch to Krita profile
        cfg.active_profile_name = "Krita"
        self.assertTrue(cfg.click_on_touch)  # Krita retains its own click_on_touch=True
        self.assertEqual(cfg.stroke_smoothing, 0.15)  # Krita retains its own smoothing
        self.assertEqual(cfg.button_primary, "right_click")

        # Modify Krita
        cfg.stroke_smoothing = 0.25
        self.assertEqual(cfg.profiles["Krita"].stroke_smoothing, 0.25)
        self.assertEqual(cfg.profiles["Default"].stroke_smoothing, 0.45)  # Default unchanged

        # 3. Serialization retains all profile customizations
        data = cfg.to_dict()
        loaded = TabletConfig.from_dict(data)
        self.assertFalse(loaded.profiles["Default"].click_on_touch)
        self.assertEqual(loaded.profiles["Default"].stroke_smoothing, 0.45)
        self.assertTrue(loaded.profiles["Krita"].click_on_touch)
        self.assertEqual(loaded.profiles["Krita"].stroke_smoothing, 0.25)

    def test_gui_profile_loading(self):
        """Test MainWindow profile loading and UI control synchronization."""
        from server.gui import MainWindow
        win = MainWindow()
        try:
            self.assertEqual(win.tabs.count(), 4)
            # Switch to osu!
            for i in range(win.combo_profiles.count()):
                if win.combo_profiles.itemData(i) == "osu!":
                    win.combo_profiles.setCurrentIndex(i)
                    break
            self.assertFalse(win.chk_click_on_touch.isChecked())

            # Switch to Default
            win.combo_profiles.setCurrentIndex(0)
            self.assertTrue(win.chk_click_on_touch.isChecked())

            # Toggle Click on Touch on Default
            win.chk_click_on_touch.setChecked(False)
            self.assertFalse(win.config.click_on_touch)
            self.assertFalse(win.config.profiles["Default"].click_on_touch)
        finally:
            win.worker.stop_server()
            win.http_server.stop()
            win.close()

    def test_barrel_button_mapping(self):
        from server.protocol import PenEvent, ACTION_DOWN, TOOL_STYLUS, BUTTON_STYLUS
        import evdev.ecodes as e

        # 1. Primary button = none
        vt = VirtualTablet(button_primary="none", mode="pointer")
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
        vt2 = VirtualTablet(button_primary="middle_click", mode="pointer")
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
            time.sleep(0.6)
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


