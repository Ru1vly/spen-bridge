"""Cross-layout profile selection must preserve edit/live profile semantics."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from profile_examples import add_example_profiles
from server.config import TabletConfig
from server.gui.main_window import MainWindow

app = QApplication.instance() or QApplication([])


class ResponsiveProfileSelectionTests(unittest.TestCase):
    def make_window(self, auto_switch):
        previous_font = app.font()
        self.addCleanup(app.setFont, previous_font)
        app.setFont(QFont(previous_font.family(), 11))
        config = TabletConfig(auto_start_server=False, auto_adb_forward=False,
                              minimize_to_tray=False, auto_switch_profiles=auto_switch)
        add_example_profiles(config)
        with patch("server.gui.main_window.load_config", return_value=config), \
             patch("server.gui.main_window.WindowWatcher.start"), \
             patch("server.gui.main_window.GuiState", return_value=Mock(last_tab_index=0, last_editing_profile="Default")):
            window = MainWindow()
        window.show()
        window.resize(760, 640)
        app.processEvents()
        self.addCleanup(self.cleanup_window, window)
        return window

    @staticmethod
    def cleanup_window(window):
        window.diag_timer.stop()
        window.system_tab.connection_panel.stop_usb_monitor()
        window.worker.shutdown()
        window.tray.tray_icon.hide()
        window.hide()
        window.deleteLater()
        app.processEvents()

    def test_auto_switch_edit_target_survives_layout_changes_without_changing_live_profile(self):
        window = self.make_window(True)
        window.tabs.setCurrentIndex(2)
        app.processEvents()
        panel = window.profiles_tab.list_panel
        self.assertTrue(panel.combo_compact.isVisible())
        panel.combo_compact.setCurrentIndex(panel.combo_compact.findData("Krita"))
        self.assertEqual(window.profiles_tab.editor_panel.current_profile_name, "Krita")
        self.assertEqual(panel.selected_profile_name(), "Krita")
        self.assertEqual(window.config.active_profile_name, "Default")
        # Native Windows fonts can keep 1200px below the em-based breakpoint.
        # Force a wide offscreen window even on a small hosted-runner screen.
        minimum_width = window.minimumWidth()
        wide_width = max(1600, window.profile_manager.fontMetrics().horizontalAdvance("M") * 90 + 400)
        window.setMinimumWidth(wide_width)
        window.resize(wide_width, 900)
        app.processEvents()
        self.assertTrue(panel.list_widget.isVisible())
        self.assertFalse(panel.combo_compact.isVisible())
        window.profiles_tab.select_profile("Blender")
        window.setMinimumWidth(minimum_width)
        window.resize(760, 640)
        app.processEvents()
        self.assertEqual(panel.combo_compact.currentData(), "Blender")
        self.assertEqual(window.profiles_tab.editor_panel.current_profile_name, "Blender")
        self.assertEqual(window.config.active_profile_name, "Default")
        self.assertFalse(window._dirty)

    def test_manual_compact_selection_applies_once_and_header_stays_in_sync(self):
        window = self.make_window(False)
        panel = window.profiles_tab.list_panel
        with patch.object(window.worker, "apply_config") as apply:
            panel.combo_compact.setCurrentIndex(panel.combo_compact.findData("Krita"))
            self.assertEqual(window.config.active_profile_name, "Krita")
            self.assertEqual(window.header_bar.combo_profiles.currentData(), "Krita")
            self.assertEqual(window.profiles_tab.editor_panel.current_profile_name, "Krita")
            self.assertEqual(apply.call_count, 1)
        window.header_bar.combo_profiles.setCurrentIndex(window.header_bar.combo_profiles.findData("Default"))
        self.assertEqual(panel.combo_compact.currentData(), "Default")
        self.assertEqual(panel.selected_profile_name(), "Default")

    def test_keyboard_navigation_and_profile_selection_work_in_tabs_and_rail(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = self.make_window(False)
        for width in (760, 1200):
            window.resize(width, 900)
            window.show()
            app.processEvents()
            navigation = window.tabs
            navigation.setCurrentIndex(0)
            compact = navigation.compact_tabs.isVisible()
            control = navigation.compact_tabs if compact else navigation.list
            control.setFocus()
            for expected in (1, 2, 3):
                QTest.keyClick(control, Qt.Key_Right if compact else Qt.Key_Down)
                self.assertEqual(navigation.currentIndex(), expected)
                self.assertEqual(navigation.list.currentRow(), expected)
                self.assertEqual(navigation.compact_tabs.currentIndex(), expected)
        window.tabs.setCurrentIndex(1)
        selector = window.profiles_tab.edit_selector
        selector.setFocus()
        selector.setCurrentIndex(selector.findData("Default"))
        with patch.object(window.worker, "apply_config") as apply:
            QTest.keyClick(selector, Qt.Key_Down)
            self.assertEqual(window.config.active_profile_name, "osu!")
            self.assertEqual(window.profiles_tab.editor_panel.current_profile_name, "osu!")
            self.assertEqual(window.header_bar.combo_profiles.currentData(), "osu!")
            apply.assert_called_once()


class WorkspaceStateMigrationTests(unittest.TestCase):
    def test_old_tabs_reopen_the_same_task_and_new_workspace_selection_is_separate(self):
        from server.gui.state import GuiState
        for old, expected in ((0, 1), (1, 0)):
            with self.subTest(old_tab=old):
                values = {"last_tab_index": old}
                store = Mock()
                store.value.side_effect = lambda key, default=None: values.get(key, default)
                with patch("server.gui.state.QSettings", return_value=store):
                    state = GuiState()
                    self.assertEqual(state.last_tab_index, expected)
                    state.last_tab_index = 3
                    store.setValue.assert_called_once_with("last_workspace_index", 3)
