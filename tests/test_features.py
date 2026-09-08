import sys
import unittest

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for Qt widgets
app = QApplication.instance() or QApplication(sys.argv)

from server.config import TabletConfig
from server.monitors import detect_monitors
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
            self.assertEqual(win.tabs.count(), 2)

            # Auto-switch off so selecting a profile also drives the live/active
            # profile (deterministic: with auto-switch on, selection only changes
            # the edit target, per the profile/editing decoupling in main_window.py).
            win.config.auto_switch_profiles = False
            win.profiles_tab.list_panel.chk_auto_switch.setChecked(False)

            # Switch to osu!
            win.profiles_tab.select_profile("osu!")
            device_section = win.profiles_tab.editor_panel.device_section
            self.assertFalse(device_section.chk_click_on_touch.isChecked())

            # Switch to Default
            win.profiles_tab.select_profile("Default")
            self.assertTrue(device_section.chk_click_on_touch.isChecked())

            # Toggle Click on Touch on Default
            device_section.chk_click_on_touch.setChecked(False)
            self.assertFalse(win.config.click_on_touch)
            self.assertFalse(win.config.profiles["Default"].click_on_touch)
        finally:
            win.worker.stop_server()
            # Toggling settings above legitimately dirties the in-memory config;
            # this test isn't exercising the unsaved-changes close prompt, so
            # skip it and close directly.
            win._dirty = False
            win.close()


if __name__ == "__main__":
    unittest.main()
