"""
Main application window: thin orchestrator that wires the header, the two
tabs (Profiles / Connection), the background server worker, and
the system tray together. Screen/section widgets own their own controls;
this module owns cross-cutting state (which profile is being edited vs.
live, dirty tracking, save/quit flows).
"""

import copy
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QTimer, Signal, QSignalBlocker, Qt
from PySide6.QtGui import QIcon, QKeySequence, QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox, QDialog, QLabel, QScrollArea

from server.config import AppProfile, TabletConfig, load_config, save_config, CONFIG_FILE_PATH
from server.protocol import PenEvent, ACTION_CANCEL, valid_event
from server.settings import listener_address
from server.window_watcher import WindowWatcher

from server.gui import theme
from server.gui.state import GuiState
from server.gui.server_worker import ServerWorker
from server.gui.network_info import get_local_ip
from server.gui.header_bar import HeaderBar
from server.gui.tray import SystemTrayController
from server.gui.dialogs import NewProfileDialog, DuplicateProfileDialog
from server.gui.profiles_tab import ProfilesTab, ProfileManager
from server.gui.widgets.workspace_navigation import WorkspaceNavigation
from server.gui.system_tab import SystemTab

logger = logging.getLogger("SPenGUI")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DIAG_TIMER_INTERVAL_MS = 33  # ~30 Hz
WINDOW_POLL_INTERVAL_MS = 300


class MainWindow(QMainWindow):
    # Marshals WindowWatcher's background-thread callback onto the GUI
    # thread - Qt auto-detects the emitting thread differs from this
    # QObject's thread affinity and queues the delivery, same pattern as
    # ServerWorker.sig_pen_event.
    sig_active_window_changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("S Pen Bridge: Tablet Controller")
        self.resize(1200, 760)
        self.setMinimumSize(760, 540)

        self.config = load_config()
        self.local_ip = get_local_ip()
        self.gui_state = GuiState()
        self._dirty = False
        self._closing = False
        self._startup_timers = []
        self._initializing = True
        self._last_detected_app: Tuple[str, str] = ("", "")

        icon_path = REPO_ROOT / "spen_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Background server worker
        self.worker = ServerWorker(self.config)
        self.worker.sig_status.connect(self.on_server_status)
        self.worker.sig_client_connected.connect(self.on_client_connected)
        self.worker.sig_client_disconnected.connect(self.on_client_disconnected)
        self.worker.sig_stats.connect(self.on_server_stats)
        self.worker.sig_pen_events_ready.connect(self.on_pen_events_ready)

        # Latest pen event cache, throttled to ~30 Hz for the diagnostics UI
        self._latest_pen_event: Optional[PenEvent] = None
        self._latest_cal_p = 0
        self._latest_abs_x = 0
        self._latest_abs_y = 0
        self.diag_timer = QTimer(self)
        self.diag_timer.setInterval(DIAG_TIMER_INTERVAL_MS)
        self.diag_timer.timeout.connect(self.update_live_diagnostics)
        self.diag_timer.start()

        # Active window auto-switch watcher. Polls (and spawns per-poll
        # subprocesses like xprop/swaymsg/hyprctl on Linux) on a background
        # thread via WindowWatcher - NOT a GUI-thread QTimer - so a slow
        # poll can never block repaints or input for the whole app.
        self.sig_active_window_changed.connect(self._check_active_window)
        self.window_watcher = WindowWatcher(
            callback=lambda app_id, title: self.sig_active_window_changed.emit(app_id, title),
            poll_interval=WINDOW_POLL_INTERVAL_MS / 1000.0,
        )
        self.window_watcher.start()

        theme.configure(QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        self.setStyleSheet(theme.build_stylesheet())
        self._init_ui()
        self.tray = SystemTrayController(self, REPO_ROOT / "spen_icon.png")
        self.worker.sig_log.connect(self.system_tab.log_panel.log)
        self._tablet_connected = False
        self.system_tab.connection_panel.connection_type_changed.connect(self._refresh_connection_type)
        self._initializing = False
        if self.config.recovery_notice:
            self.system_tab.log_panel.log(self.config.recovery_notice)
            self._mark_dirty()

        self._save_shortcut = QAction(self)
        self._save_shortcut.setShortcut(QKeySequence("Ctrl+S"))
        self._save_shortcut.triggered.connect(self.save_all_settings)
        self.addAction(self._save_shortcut)

        if self.config.auto_start_server:
            self._schedule_startup(400, self.start_server)
        if self.config.auto_adb_forward:
            self._schedule_startup(600, lambda: self.system_tab.connection_panel.run_adb_reverse(silent=True))

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _schedule_startup(self, delay, operation):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: operation() if not self._closing else None)
        timer.start(delay)
        self._startup_timers.append(timer)

    def _cancel_startup(self):
        for timer in self._startup_timers:
            timer.stop()
        self._startup_timers.clear()

    def _init_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self.header_bar = HeaderBar()
        self.header_bar.server_toggle_clicked.connect(self.toggle_server)
        self.header_bar.save_clicked.connect(self.save_all_settings)
        self.header_bar.profile_changed.connect(self._on_profile_selection_changed)
        layout.addWidget(self.header_bar)
        self.recovery_label = QLabel(self.config.recovery_notice)
        self.recovery_label.setTextFormat(Qt.PlainText)
        self.recovery_label.setWordWrap(True)
        self.recovery_label.setVisible(bool(self.config.recovery_notice))
        layout.addWidget(self.recovery_label)

        self.profiles_tab = ProfilesTab(self.config, self.worker)
        self.profiles_tab.profile_selected.connect(self._on_profile_selection_changed)
        self.profiles_tab.editor_panel.profile_dirty.connect(self._mark_dirty)
        self.profiles_tab.list_panel.chk_auto_switch.toggled.connect(self._on_auto_switch_toggled)
        self.profiles_tab.list_panel.btn_new_profile.clicked.connect(self._on_new_profile)
        self.profiles_tab.list_panel.btn_duplicate_profile.clicked.connect(self._on_duplicate_profile)
        self.profiles_tab.list_panel.btn_del_prof.clicked.connect(self._on_delete_profile)

        self.system_tab = SystemTab(self.local_ip, self.config)
        self.system_tab.startup_panel.reset_requested.connect(self._reset_defaults)
        self.system_tab.startup_panel.changed.connect(self._on_system_settings_changed)
        self.system_tab.startup_panel.device_name_changed.connect(lambda: self.worker.apply_config(self.config))
        self.profiles_tab.editor_panel.mapping_section.monitors_refreshed.connect(
            self.system_tab.startup_panel.set_desktop_size
        )

        self.profile_manager = ProfileManager(self.profiles_tab)
        self.preferences_page = QScrollArea()
        self.preferences_page.setWidgetResizable(True)
        preferences = QWidget()
        preferences_layout = QVBoxLayout(preferences)
        preferences_layout.setContentsMargins(0, 0, 8, 8)
        title = QLabel("Preferences")
        title.setObjectName("workspaceTitle")
        preferences_layout.addWidget(title)
        preferences_layout.addWidget(self.system_tab.startup_panel)
        from server.gui.support_panel import SupportPanel
        self.support_panel = SupportPanel(self.config)
        self.support_panel.body_layout().addWidget(self.system_tab.log_panel)
        preferences_layout.addWidget(self.support_panel)
        preferences_layout.addStretch()
        self.preferences_page.setWidget(preferences)
        self.tabs = WorkspaceNavigation()
        self.tabs.addTab(self.system_tab, "Connection")
        self.tabs.addTab(self.profiles_tab, "Pen settings")
        self.tabs.addTab(self.profile_manager, "App profiles")
        self.tabs.addTab(self.preferences_page, "Preferences")
        self.tabs.setFooter(self.header_bar.profile_context)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.profiles_tab.manage_requested.connect(lambda: self.tabs.setCurrentIndex(2))
        self.profile_manager.tune_requested.connect(lambda: self.tabs.setCurrentIndex(1))
        layout.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        theme.apply_elevation_to_cards(self)

        # Initial state (blockSignals so restoring saved config never marks the
        # document dirty: only real user edits should trigger the save prompt)
        chk_auto_switch = self.profiles_tab.list_panel.chk_auto_switch
        chk_auto_switch.blockSignals(True)
        chk_auto_switch.setChecked(self.config.auto_switch_profiles)
        chk_auto_switch.blockSignals(False)
        self.header_bar.set_auto_switch_mode(self.config.auto_switch_profiles)
        self.system_tab.startup_panel.set_desktop_size(self.profiles_tab.editor_panel.mapping_section.desktop_size)

        self._repopulate_profiles()
        initial_profile = (self.gui_state.last_editing_profile if self.config.auto_switch_profiles
                           else self.config.active_profile_name)
        if initial_profile not in self.config.profiles:
            initial_profile = self.config.active_profile_name
        self.profiles_tab.select_profile(initial_profile)

        self.tabs.setCurrentIndex(self.gui_state.last_tab_index)

        # Nothing up to this point is a real user edit: start clean.
        self._dirty = False
        self.header_bar.set_dirty(False)

    # ------------------------------------------------------------------
    # Profile switching (see GUI redesign spec section 3)
    # ------------------------------------------------------------------
    def _on_profile_selection_changed(self, name: str):
        if name not in self.config.profiles:
            return
        self.set_editing_profile(name)
        if not self.config.auto_switch_profiles:
            self.set_active_profile(name)

    def set_editing_profile(self, name: str):
        """Change ONLY what is shown/edited: never touches active_profile_name."""
        profile = self.config.profiles.get(name)
        if profile is None:
            return
        self.profiles_tab.sync_selection(name)
        self.profiles_tab.editor_panel.bind_profile(profile)
        self.header_bar.set_active_profile(self.config.active_profile_name)
        # Keep the list's own selection in sync no matter what triggered the
        # edit-target change (header combo, auto-switch is exempt - see
        # set_active_profile), without re-emitting profile_selected (that
        # would re-enter this whole chain for no reason since we're already
        # mid-handling this exact profile).
        self.profiles_tab.list_panel.sync_current_by_name(name)
        self.profiles_tab.list_panel.refresh_markers(self.config.active_profile_name, name)
        can_delete = name != "Default"
        self.profiles_tab.list_panel.btn_del_prof.setEnabled(can_delete)
        self.gui_state.last_editing_profile = name

    def set_active_profile(self, name: str, *, user_initiated=True):
        """Make `name` the live profile driving the virtual tablet."""
        profile = self.config.profiles.get(name)
        if profile is None:
            return
        changed = self.config.active_profile_name != name
        self.config.active_profile_name = name
        self.worker.apply_config(self.config)
        if changed and user_initiated and not self._initializing:
            self._mark_dirty()
        self.header_bar.set_active_profile(name)
        self.profiles_tab.list_panel.refresh_markers(name, self.profiles_tab.editor_panel.current_profile_name)
        self.system_tab.diagnostics_panel.set_click_on_touch(profile.click_on_touch)

    def _on_auto_switch_toggled(self, checked: bool):
        self.config.auto_switch_profiles = checked
        self.header_bar.set_auto_switch_mode(checked)
        self.profiles_tab.list_panel.refresh_markers(
            self.config.active_profile_name, self.profiles_tab.editor_panel.current_profile_name
        )
        self._mark_dirty()
        if checked:
            profile = self.config.find_profile_for_app(*self._last_detected_app) or self.config.profiles["Default"]
            self.set_active_profile(profile.name, user_initiated=False)

    def _on_tab_changed(self, index: int):
        self.gui_state.last_tab_index = index
        if self.tabs.currentWidget() in (self.profiles_tab, self.profile_manager):
            self.profiles_tab.editor_panel.update_live_match(*self._last_detected_app)

    def _check_active_window(self, app_id: str, title: str):
        if (app_id, title) == self._last_detected_app:
            return
        self._last_detected_app = (app_id, title)

        display_name = app_id or title or "Desktop"
        if len(display_name) > 28:
            display_name = display_name[:26] + "…"
        self.profiles_tab.list_panel.lbl_focused_window.setText(f"Active Window: {display_name}")

        if self.tabs.currentWidget() in (self.profiles_tab, self.profile_manager):
            self.profiles_tab.editor_panel.update_live_match(app_id, title)

        if self.config.auto_switch_profiles:
            matched_profile = self.config.find_profile_for_app(app_id, title) or self.config.profiles["Default"]
            if matched_profile and matched_profile.name != self.config.active_profile_name:
                self.set_active_profile(matched_profile.name, user_initiated=False)
                self.system_tab.log_panel.log(f"Active tablet profile: {matched_profile.name}")

    # ------------------------------------------------------------------
    # Profile management (new / duplicate / delete)
    # ------------------------------------------------------------------
    def _repopulate_profiles(self):
        names = list(self.config.profiles.keys())
        self.header_bar.populate_profiles(names, self.config.active_profile_name)
        self.profiles_tab.populate(names, self.profiles_tab.editor_panel.current_profile_name)
        self.profiles_tab.list_panel.repopulate(
            self.config.active_profile_name, self.profiles_tab.editor_panel.current_profile_name
        )

    def _on_new_profile(self):
        dlg = NewProfileDialog(list(self.config.profiles.keys()), self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.profile_name
        if name in self.config.profiles:
            QMessageBox.warning(self, "Profile Exists", f"A profile named '{name}' already exists.")
            return

        source = self.config.profiles.get(dlg.source_profile_name) or self.config.profiles["Default"]
        new_prof = AppProfile(
            name=name,
            app_matches=[name.lower()],
            click_on_touch=source.click_on_touch,
            device_mode=source.device_mode,
            direct_mode=source.direct_mode,
            mapping_mode=source.mapping_mode,
            selected_monitor=source.selected_monitor,
            custom_bounds=list(source.custom_bounds),
            pressure_curve_type=source.pressure_curve_type,
            pressure_gamma=source.pressure_gamma,
            pressure_min=source.pressure_min,
            pressure_max=source.pressure_max,
            stroke_smoothing=source.stroke_smoothing,
            button_primary=source.button_primary,
            button_secondary=source.button_secondary,
        )
        self.config.profiles[name] = new_prof
        self._repopulate_profiles()
        self.profiles_tab.select_profile(name)
        self.profiles_tab.editor_panel.identity_section.chip_input.focus_input()
        self.system_tab.log_panel.log(f"Created application profile: {name}")
        self._mark_dirty()

    def _on_duplicate_profile(self):
        current_name = self.profiles_tab.list_panel.selected_profile_name()
        if not current_name:
            return
        dlg = DuplicateProfileDialog(current_name, self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_name = dlg.new_name
        if new_name in self.config.profiles:
            QMessageBox.warning(self, "Profile Exists", f"A profile named '{new_name}' already exists.")
            return

        new_prof = copy.deepcopy(self.config.profiles[current_name])
        new_prof.name = new_name
        self.config.profiles[new_name] = new_prof
        self._repopulate_profiles()
        self.profiles_tab.select_profile(new_name)
        self.system_tab.log_panel.log(f"Duplicated profile '{current_name}' as '{new_name}'")
        self._mark_dirty()

    def _on_delete_profile(self):
        name = self.profiles_tab.list_panel.selected_profile_name()
        if not name or name == "Default":
            return
        ans = QMessageBox.question(self, "Delete Profile", f"Are you sure you want to delete profile '{name}'?")
        if ans != QMessageBox.Yes:
            return
        if name == self.config.active_profile_name:
            self.set_active_profile("Default")
        del self.config.profiles[name]
        self._repopulate_profiles()
        self.profiles_tab.select_profile("Default")
        self.system_tab.log_panel.log(f"Deleted profile: {name}")
        self._mark_dirty()

    # ------------------------------------------------------------------
    # Dirty / save / reset
    # ------------------------------------------------------------------
    def _mark_dirty(self):
        self._dirty = True
        self.header_bar.set_dirty(True)
        self.profiles_tab.list_panel.refresh_customized_badge(self.profiles_tab.editor_panel.current_profile_name)

    def _on_system_settings_changed(self):
        self._mark_dirty()
        self.system_tab.connection_panel.refresh_ip_label()

    def save_all_settings(self, checked=False, *, quiet=False):
        try:
            self.config.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Check Settings", str(error))
            return False
        if not save_config(self.config):
            QMessageBox.warning(self, "Settings Not Saved",
                                "The settings file could not be replaced. Your changes remain open; check disk space and permissions, then save again.")
            return False
        self._dirty = False
        self.header_bar.set_dirty(False)
        self.config.recovery_notice = ""
        self.recovery_label.hide()
        self.system_tab.log_panel.log("Configuration saved successfully.")
        self.header_bar.save_feedback.setText("Settings saved")
        return True

    def _reset_defaults(self):
        ans = QMessageBox.question(self, "Reset Defaults", "Reset all tablet settings to default values?")
        if ans != QMessageBox.Yes:
            return
        candidate = TabletConfig()
        self._cancel_startup()
        try:
            self.worker.shutdown()
        except TimeoutError as error:
            QMessageBox.warning(self, "Reset Not Completed", str(error))
            return
        if not save_config(candidate):
            QMessageBox.warning(self, "Reset Not Saved", "Your previous settings are still active. Check disk space and permissions, then try again.")
            return
        self.system_tab.connection_panel.stop_usb_monitor()
        self.recovery_label.hide()
        self.config = candidate
        self.worker.config = candidate
        self.support_panel.refresh_report(candidate)
        self.system_tab.startup_panel._config = candidate
        self.system_tab.connection_panel._config = candidate
        self.system_tab.startup_panel._sync_from_config()
        self.system_tab.connection_panel.refresh_ip_label()
        self.profiles_tab.list_panel._config = candidate
        editor = self.profiles_tab.editor_panel
        editor._config = candidate
        editor.mapping_section._config = candidate
        editor.mapping_section._sync_global_controls()
        checkbox = self.profiles_tab.list_panel.chk_auto_switch
        with QSignalBlocker(checkbox):
            checkbox.setChecked(candidate.auto_switch_profiles)
        self.header_bar.set_auto_switch_mode(candidate.auto_switch_profiles)
        self._repopulate_profiles()
        self.set_editing_profile("Default")
        self.set_active_profile("Default")
        self._dirty = False
        self.header_bar.set_dirty(False)
        QMessageBox.information(self, "Settings Reset", "Settings have been reset and saved. The server is stopped; start it when you are ready.")

    # ------------------------------------------------------------------
    # Server control & tests
    # ------------------------------------------------------------------
    def toggle_server(self):
        if self.worker._is_running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        if self._closing or self.worker.state != "stopped":
            return
        self.system_tab.log_panel.log(f"Starting paired TLS server on {listener_address(self.config)}:{self.config.port}...")
        self.header_bar.btn_server_toggle.setText("Starting...")
        self.header_bar.btn_server_toggle.setEnabled(False)
        self.system_tab.connection_panel.set_transitioning()
        self.worker.start_server()

    def stop_server(self):
        if self.worker.state not in ("running", "starting"):
            return
        self.system_tab.connection_panel.set_transitioning()
        self.system_tab.log_panel.log("Stopping server...")
        self.header_bar.btn_server_toggle.setText("Stopping...")
        self.header_bar.btn_server_toggle.setEnabled(False)
        self.worker.stop_server()

    def on_server_status(self, status: str, message: str):
        self.system_tab.log_panel.log(f"Server Status: {status} ({message})")
        self.header_bar.btn_server_toggle.setEnabled(True)
        self.system_tab.connection_panel.set_listener(self.worker.listener_endpoint)

        if status == "running":
            self.header_bar.set_server_status("running", f"Listening (Port {self.worker.listener_endpoint[1] if self.worker.listener_endpoint else self.config.port})")
        elif status == "stopped":
            self.header_bar.set_server_status("stopped", "Server stopped")
            self._reset_diagnostics()
        elif status == "error":
            self.header_bar.set_server_status("error", message)
            QMessageBox.critical(self, "Server Error", message)

    def on_client_connected(self, client_addr: str):
        self._tablet_connected = True
        self.system_tab.log_panel.log(f"Tablet connected from {client_addr}")
        self.system_tab.connection_panel.set_client(client_addr)
        self.tray.notify("S Pen Connected", f"Tablet connected from {client_addr}")

    def _refresh_connection_type(self):
        if self._tablet_connected:
            kind = self.system_tab.connection_panel.connection_type()
            if kind:
                self.header_bar.set_server_status("connected", f"Connected via {kind}")

    def on_client_disconnected(self, client_addr: str):
        self._tablet_connected = False
        self.system_tab.connection_panel.set_client(None)
        self.system_tab.log_panel.log(f"Tablet disconnected: {client_addr}")
        if self.worker._is_running:
            self.header_bar.set_server_status("running", f"Listening (Port {self.worker.listener_endpoint[1] if self.worker.listener_endpoint else self.config.port})")
        self._reset_diagnostics()

    def on_server_stats(self, rate: float, packets: int, total_events: int):
        self.system_tab.diagnostics_panel.update_traffic(rate, packets)

    def on_pen_events_ready(self):
        for record in self.worker.drain_pen_events():
            self.on_pen_event(*record)

    def on_pen_event(self, ev: PenEvent, cal_p: int, abs_x: int, abs_y: int):
        if not valid_event(ev):
            return
        self._latest_pen_event, self._latest_cal_p = ev, cal_p
        self._latest_abs_x, self._latest_abs_y = abs_x, abs_y

    def update_live_diagnostics(self):
        ev, self._latest_pen_event = self._latest_pen_event, None
        if ev is not None:
            cal_p = self._latest_cal_p
            self.system_tab.diagnostics_panel.update_pen_event(ev, cal_p, self._latest_abs_x, self._latest_abs_y)
            ceiling = 32767 if sys.platform == "win32" else 4095
            pressure = self.profiles_tab.editor_panel.pressure_section
            pressure.curve_widget.set_current_pressure(ev.pressure, cal_p / ceiling)
            pressure.bar_raw.setValue(int(ev.pressure * 100))
            pressure.bar_cal.setValue(int(cal_p / ceiling * 100))

    def _reset_diagnostics(self):
        self._latest_pen_event = PenEvent(ACTION_CANCEL, 0, 0, 0, 0, 0)
        self._latest_cal_p = self._latest_abs_x = self._latest_abs_y = 0
        self.system_tab.diagnostics_panel.update_traffic(0, 0)
        self.update_live_diagnostics()

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        if self.config.minimize_to_tray and self.tray.tray_icon.isSystemTrayAvailable() and self.tray.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray.notify("S Pen Bridge", "Application minimized to system tray.")
            return

        if not self._confirm_unsaved():
            event.ignore()
            return
        if self.force_quit(discard_confirmed=True) is False:
            event.ignore()

    def _confirm_unsaved(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "Unsaved Changes", "You have unsaved changes. Save before quitting?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_all_settings(quiet=True)
        return True

    def force_quit(self, checked=False, *, discard_confirmed=False):
        if not discard_confirmed and not self._confirm_unsaved():
            return False
        self._closing = True
        self._cancel_startup()
        self.window_watcher.stop()
        try:
            self.worker.shutdown()
        except TimeoutError as error:
            self._closing = False
            QMessageBox.critical(self, "Input Cleanup Incomplete", f"{error}. The application will stay open so cleanup can finish. Try quitting again shortly.")
            return False
        self.system_tab.connection_panel.stop_usb_monitor()
        self.diag_timer.stop()
        QApplication.quit()
        return True
