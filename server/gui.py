"""
S Pen on Linux — Modern Desktop GUI Application.
Built with PySide6 (Qt 6).
Features live pressure tuning, display mapping, interactive scratchpad,
QR code pairing, ADB USB forwarder, and system tray integration.
"""

import asyncio
import http.server
import logging
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading
import time
from typing import Optional, List, Dict, Any

from PySide6.QtCore import (
    Qt,
    QObject,
    Signal,
    Slot,
    QTimer,
    QThread,
)
from PySide6.QtGui import (
    QIcon,
    QPixmap,
    QImage,
    QColor,
    QFont,
    QAction,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QCheckBox,
    QLineEdit,
    QSpinBox,
    QProgressBar,
    QTextEdit,
    QGroupBox,
    QFrame,
    QMessageBox,
    QSystemTrayIcon,
    QMenu,
    QButtonGroup,
    QRadioButton,
    QSplitter,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
)

import qrcode
from PIL import Image

from server.config import TabletConfig, AppProfile, load_config, save_config, CONFIG_FILE_PATH
from server.monitors import detect_monitors
from server.virtual_tablet import VirtualTablet
from server.server import SPenServer
from server.protocol import PenEvent
from server.widgets.pressure_curve import PressureCurveWidget
from server.widgets.monitor_layout import MonitorLayoutWidget
from server.widgets.scratchpad import ScratchpadWidget
from server.window_watcher import get_active_window

logger = logging.getLogger("SPenGUI")

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_local_ip() -> str:
    """Detect local LAN IP address."""
    try:
        res = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        parts = res.stdout.split()
        if "src" in parts:
            idx = parts.index("src")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ----------------------------------------------------------------------
# Background Server Thread
# ----------------------------------------------------------------------
class ServerWorker(QObject):
    sig_status = Signal(str, str)             # state ("running", "stopped", "error"), message
    sig_client_connected = Signal(str)        # client address
    sig_client_disconnected = Signal(str)     # client address
    sig_stats = Signal(float, int, int)       # rate, packets, total_events
    sig_pen_event = Signal(object, int, int, int)  # ev, cal_p, abs_x, abs_y
    sig_log = Signal(str)

    def __init__(self, config: TabletConfig):
        super().__init__()
        self.config = config
        self.tablet: Optional[VirtualTablet] = None
        self.server: Optional[SPenServer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def start_server(self):
        if self._is_running:
            return

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Detect monitors to calculate mapping
        monitors, desk_size = detect_monitors()
        sb, desk = self.config.get_screen_bounds_and_desktop(monitors)

        try:
            self.tablet = VirtualTablet(
                name=self.config.device_name,
                mode=self.config.device_mode,
                direct_mode=self.config.direct_mode,
                screen_bounds=sb,
                desktop_size=desk,
                click_on_touch=self.config.click_on_touch,
                pressure_curve_type=self.config.pressure_curve_type,
                pressure_gamma=self.config.pressure_gamma,
                pressure_min=self.config.pressure_min,
                pressure_max=self.config.pressure_max,
                stroke_smoothing=self.config.stroke_smoothing,
                button_primary=self.config.button_primary,
                button_secondary=self.config.button_secondary,
                aspect_ratio_lock=self.config.aspect_ratio_lock,
                tablet_aspect_ratio=self.config.tablet_aspect_ratio,
                on_event_processed=self._on_tablet_event,
            )
        except Exception as e:
            self.sig_status.emit("error", f"Failed to create VirtualTablet: {e}")
            return

        self.server = SPenServer(
            tablet=self.tablet,
            host=self.config.host,
            port=self.config.port,
            on_client_connected=lambda c: self.sig_client_connected.emit(c),
            on_client_disconnected=lambda c: self.sig_client_disconnected.emit(c),
            on_stats=lambda r, p, t: self.sig_stats.emit(r, p, t),
        )

        async def _async_start():
            await self.server.start()
            self._is_running = True
            self.sig_status.emit("running", f"Listening on {self.config.host}:{self.config.port}")
            while self._is_running:
                await asyncio.sleep(0.5)
            await self.server.stop()
            self.tablet.close()

        try:
            self._loop.run_until_complete(_async_start())
        except Exception as e:
            self.sig_status.emit("error", f"Server error: {e}")
        finally:
            self._is_running = False
            self.sig_status.emit("stopped", "Server stopped")

    def _on_tablet_event(self, ev: PenEvent, cal_p: int, abs_x: int, abs_y: int):
        self.sig_pen_event.emit(ev, cal_p, abs_x, abs_y)

    def stop_server(self):
        if not self._is_running:
            return
        self._is_running = False

    def update_tablet_settings(self, **kwargs):
        if self.tablet:
            self.tablet.update_settings(**kwargs)

    def set_device_mode(
        self,
        mode: Optional[str] = None,
        direct_mode: Optional[bool] = None,
        device_name: Optional[str] = None,
    ):
        """Hot-swap the virtual tablet device when switching mode or direct mode."""
        target_mode = mode if mode is not None else self.config.device_mode
        target_direct = direct_mode if direct_mode is not None else self.config.direct_mode
        target_name = device_name if device_name is not None else self.config.device_name

        if (
            self.tablet is not None
            and self.tablet.mode == target_mode
            and self.tablet.direct_mode == target_direct
            and self.tablet.name == target_name
        ):
            return

        if self.tablet is None:
            return

        monitors, _ = detect_monitors()
        sb, desk = self.config.get_screen_bounds_and_desktop(monitors)

        try:
            new_tablet = VirtualTablet(
                name=target_name,
                mode=target_mode,
                direct_mode=target_direct,
                screen_bounds=sb,
                desktop_size=desk,
                click_on_touch=self.config.click_on_touch,
                pressure_curve_type=self.config.pressure_curve_type,
                pressure_gamma=self.config.pressure_gamma,
                pressure_min=self.config.pressure_min,
                pressure_max=self.config.pressure_max,
                stroke_smoothing=self.config.stroke_smoothing,
                button_primary=self.config.button_primary,
                button_secondary=self.config.button_secondary,
                aspect_ratio_lock=self.config.aspect_ratio_lock,
                tablet_aspect_ratio=self.config.tablet_aspect_ratio,
                on_event_processed=self._on_tablet_event,
            )
            old_tablet = self.tablet
            self.tablet = new_tablet
            if self.server:
                self.server.tablet = new_tablet
            if old_tablet:
                old_tablet.close()
            logger.info(f"Hot-swapped VirtualTablet device to mode='{target_mode}', direct_mode={target_direct}")
        except Exception as e:
            logger.error(f"Failed to hot-swap VirtualTablet: {e}")


# ----------------------------------------------------------------------
# Background Mini HTTP Server for APK Download
# ----------------------------------------------------------------------
class MiniHttpServer:
    def __init__(self, port=8080, directory=str(REPO_ROOT)):
        self.port = port
        self.directory = directory
        self.httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.httpd is not None:
            return

        directory = self.directory

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, format, *args):
                pass  # suppress console spam

        socketserver.TCPServer.allow_reuse_address = True
        try:
            self.httpd = socketserver.TCPServer(("0.0.0.0", self.port), Handler)
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"APK download HTTP server listening on port {self.port}")
        except Exception as e:
            logger.warning(f"Could not start APK HTTP server: {e}")

    def stop(self):
        if self.httpd:
            try:
                self.httpd.server_close()
            except Exception:
                pass
            try:
                threading.Thread(target=self.httpd.shutdown, daemon=True).start()
            except Exception:
                pass
            self.httpd = None


# ----------------------------------------------------------------------
# Main Application Window
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("S Pen on Linux — Tablet Controller")
        self.resize(1000, 680)
        self.setMinimumSize(850, 580)

        self.config = load_config()
        self.local_ip = get_local_ip()

        icon_path = REPO_ROOT / "spen_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Background server worker
        self.worker = ServerWorker(self.config)
        self.worker.sig_status.connect(self.on_server_status)
        self.worker.sig_client_connected.connect(self.on_client_connected)
        self.worker.sig_client_disconnected.connect(self.on_client_disconnected)
        self.worker.sig_stats.connect(self.on_server_stats)
        self.worker.sig_pen_event.connect(self.on_pen_event)

        # Background HTTP server for APK
        self.http_server = MiniHttpServer(8080, str(REPO_ROOT))
        self.http_server.start()

        # Detected monitors cache
        self.monitors, self.desktop_size = detect_monitors()

        # Throttle UI diagnostic refresh to 30 FPS
        self._latest_pen_event = None
        self._latest_cal_p = 0
        self._latest_abs_x = 0
        self._latest_abs_y = 0
        self.diag_timer = QTimer(self)
        self.diag_timer.setInterval(33)  # ~30 Hz
        self.diag_timer.timeout.connect(self.update_live_diagnostics)
        self.diag_timer.start()

        # Active window auto-switch watcher
        self._loading_profile = False
        self._last_detected_app = ("", "")
        self.window_timer = QTimer(self)
        self.window_timer.setInterval(300)
        self.window_timer.timeout.connect(self._check_active_window)
        self.window_timer.start()

        # Build UI
        self._apply_dark_style()
        self._init_ui()
        self._init_tray()

        # Auto start server if configured
        if self.config.auto_start_server:
            QTimer.singleShot(400, self.start_server)

        # Auto ADB forward if configured
        if self.config.auto_adb_forward:
            QTimer.singleShot(600, self.run_adb_forward)

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------
    def _apply_dark_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Inter', 'Segoe UI', 'Ubuntu', sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background: #181825;
                border-radius: 8px;
                top: -1px;
            }
            QTabBar::tab {
                background: #1e1e2e;
                color: #a6adc8;
                padding: 9px 18px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: #181825;
                color: #89b4fa;
                border-top: 2px solid #89b4fa;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #252538;
                color: #cdd6f4;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 8px;
                margin-top: 14px;
                padding: 12px;
                background-color: #1e1e2e;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #89b4fa;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #585b70;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QPushButton#primaryBtn {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: 600;
                border: none;
            }
            QPushButton#primaryBtn:hover {
                background-color: #b4befe;
            }
            QPushButton#dangerBtn {
                background-color: #f38ba8;
                color: #11111b;
                font-weight: 600;
                border: none;
            }
            QPushButton#dangerBtn:hover {
                background-color: #eba0ac;
            }
            QPushButton#successBtn {
                background-color: #a6e3a1;
                color: #11111b;
                font-weight: 600;
                border: none;
            }
            QPushButton#successBtn:hover {
                background-color: #94e2d5;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 5px 8px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #89b4fa;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #313244;
                height: 6px;
                background: #11111b;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #cdd6f4;
                border: 1px solid #89b4fa;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
            }
            QProgressBar {
                border: 1px solid #313244;
                border-radius: 4px;
                text-align: center;
                background-color: #11111b;
                color: #cdd6f4;
                font-size: 11px;
                height: 16px;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 3px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #45475a;
                background-color: #11111b;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QRadioButton {
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 1px solid #45475a;
                background-color: #11111b;
            }
            QRadioButton::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QTextEdit {
                background-color: #11111b;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #a6adc8;
                font-family: 'JetBrains Mono', 'Fira Code', 'Monospace';
                font-size: 11px;
            }
            QListWidget {
                background-color: #11111b;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #cdd6f4;
                padding: 4px;
            }
            QListWidget::item {
                padding: 7px 10px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
                font-weight: 600;
            }
            QListWidget::item:hover:!selected {
                background-color: #181825;
            }
        """)

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # Single Clean Header Bar
        main_layout.addWidget(self._create_header_bar())

        # 4 Systematic Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_pen_tab(), "Pen && Buttons")
        self.tabs.addTab(self._create_mapping_tab(), "Display && Area")
        self.tabs.addTab(self._create_profiles_tab(), "Application Profiles")
        self.tabs.addTab(self._create_connection_tab(), "Connection && Test")

        main_layout.addWidget(self.tabs)
        self.setCentralWidget(main_widget)

        # Initialize profile selector and load active profile
        self._populate_profile_combo()
        self._load_profile_into_ui(self.config.get_active_profile())

    def _create_header_bar(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet("background: #181825; border: 1px solid #313244; border-radius: 8px; padding: 4px;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Title & Icon
        title_label = QLabel("S Pen on Linux")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #89b4fa;")
        layout.addWidget(title_label)

        # Server Status Badge
        self.status_badge = QLabel("● Server Stopped")
        self.status_badge.setStyleSheet("""
            background-color: #313244;
            color: #f38ba8;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 12px;
        """)
        layout.addWidget(self.status_badge)

        layout.addStretch()

        # Active Profile Selector
        lbl_profile = QLabel("Profile:")
        lbl_profile.setStyleSheet("color: #a6adc8; font-weight: 600; font-size: 13px;")
        layout.addWidget(lbl_profile)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(160)
        self.combo_profiles.currentIndexChanged.connect(self._on_profile_dropdown_changed)
        layout.addWidget(self.combo_profiles)

        layout.addSpacing(6)

        # Start / Stop Toggle Button
        self.btn_server_toggle = QPushButton("Start Server")
        self.btn_server_toggle.setObjectName("successBtn")
        self.btn_server_toggle.clicked.connect(self.toggle_server)
        layout.addWidget(self.btn_server_toggle)

        # Save Settings Button
        btn_save = QPushButton("Save Config")
        btn_save.clicked.connect(self.save_all_settings)
        layout.addWidget(btn_save)

        return header

    def _populate_profile_combo(self):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for name in self.config.profiles.keys():
            label = "Default (Global)" if name == "Default" else name
            self.combo_profiles.addItem(label, name)
        active = self.config.active_profile_name
        for i in range(self.combo_profiles.count()):
            if self.combo_profiles.itemData(i) == active:
                self.combo_profiles.setCurrentIndex(i)
                break
        self.combo_profiles.blockSignals(False)

        if hasattr(self, "profile_list_widget"):
            self.profile_list_widget.blockSignals(True)
            self.profile_list_widget.clear()
            for name in self.config.profiles.keys():
                label = f"★ {name} (Global Default)" if name == "Default" else name
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, name)
                self.profile_list_widget.addItem(item)
                if name == active:
                    self.profile_list_widget.setCurrentItem(item)
            self.profile_list_widget.blockSignals(False)

    def _on_profile_dropdown_changed(self, index: int):
        if getattr(self, "_loading_profile", False) or index < 0:
            return
        name = self.combo_profiles.itemData(index)
        if name and name in self.config.profiles:
            self.config.active_profile_name = name
            prof = self.config.profiles[name]
            self.log(f"Active profile: {name}")
            self._load_profile_into_ui(prof)

    def _on_profile_list_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem] = None):
        if getattr(self, "_loading_profile", False) or not current:
            return
        name = current.data(Qt.UserRole)
        if name and name in self.config.profiles:
            self.config.active_profile_name = name
            prof = self.config.profiles[name]
            self.log(f"Active profile: {name}")
            self._load_profile_into_ui(prof)

    def _create_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Application Profile", "Enter profile name (e.g. Krita, Blender, Game):")
        if not ok or not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.config.profiles:
            QMessageBox.warning(self, "Profile Exists", f"A profile named '{name}' already exists.")
            return

        cur_prof = self.config.get_active_profile()
        new_prof = AppProfile(
            name=name,
            app_matches=[name.lower()],
            click_on_touch=cur_prof.click_on_touch,
            device_mode=cur_prof.device_mode,
            mapping_mode=cur_prof.mapping_mode,
            selected_monitor=cur_prof.selected_monitor,
            custom_bounds=list(cur_prof.custom_bounds),
            pressure_curve_type=cur_prof.pressure_curve_type,
            pressure_gamma=cur_prof.pressure_gamma,
            pressure_min=cur_prof.pressure_min,
            pressure_max=cur_prof.pressure_max,
            stroke_smoothing=cur_prof.stroke_smoothing,
            button_primary=cur_prof.button_primary,
            button_secondary=cur_prof.button_secondary,
        )
        self.config.profiles[name] = new_prof
        self.config.active_profile_name = name
        self._populate_profile_combo()
        self._load_profile_into_ui(new_prof)
        self.log(f"Created application profile: {name}")

    def _delete_current_profile(self):
        name = self.config.active_profile_name
        if name == "Default":
            QMessageBox.warning(self, "Cannot Delete", "The 'Default' global profile cannot be deleted.")
            return

        ans = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to delete profile '{name}'?",
        )
        if ans == QMessageBox.Yes:
            del self.config.profiles[name]
            self.config.active_profile_name = "Default"
            self._populate_profile_combo()
            self._load_profile_into_ui(self.config.get_active_profile())
            self.log(f"Deleted profile: {name}")

    def _on_app_matches_edited(self, text: str):
        if getattr(self, "_loading_profile", False):
            return
        matches = [m.strip() for m in text.split(",") if m.strip()]
        self.config.get_active_profile().app_matches = matches

    def _on_auto_switch_toggled(self, checked: bool):
        self.config.auto_switch_profiles = checked

    def _on_click_on_touch_toggled(self, checked: bool):
        if getattr(self, "_loading_profile", False):
            return
        self.config.click_on_touch = checked
        self.worker.update_tablet_settings(click_on_touch=checked)
        self.log(f"Click on Touch: {checked} (Profile: {self.config.active_profile_name})")

    def _check_active_window(self):
        try:
            app_id, title = get_active_window()
        except Exception:
            return

        if (app_id, title) == self._last_detected_app:
            return

        self._last_detected_app = (app_id, title)
        display_name = app_id or title or "Desktop"
        if len(display_name) > 28:
            display_name = display_name[:26] + "…"
        if hasattr(self, "lbl_focused_window"):
            self.lbl_focused_window.setText(f"Active Window: <b>{display_name}</b>")

        if self.config.auto_switch_profiles and (app_id or title):
            matched_profile = self.config.find_profile_for_app(app_id, title)
            if matched_profile and matched_profile.name != self.config.active_profile_name:
                for i in range(self.combo_profiles.count()):
                    if self.combo_profiles.itemData(i) == matched_profile.name:
                        self.combo_profiles.setCurrentIndex(i)
                        self.log(f"Auto-switched profile to '{matched_profile.name}' for window '{app_id or title}'")
                        break

    def _load_profile_into_ui(self, profile: AppProfile):
        self._loading_profile = True
        try:
            # Sync top combo
            for i in range(self.combo_profiles.count()):
                if self.combo_profiles.itemData(i) == profile.name:
                    self.combo_profiles.blockSignals(True)
                    self.combo_profiles.setCurrentIndex(i)
                    self.combo_profiles.blockSignals(False)
                    break

            # Sync profiles list widget
            if hasattr(self, "profile_list_widget"):
                for i in range(self.profile_list_widget.count()):
                    item = self.profile_list_widget.item(i)
                    if item.data(Qt.UserRole) == profile.name:
                        self.profile_list_widget.blockSignals(True)
                        self.profile_list_widget.setCurrentItem(item)
                        self.profile_list_widget.blockSignals(False)
                        break

            # Update profile rules UI
            if hasattr(self, "lbl_selected_profile_name"):
                label = "Default (Global Settings)" if profile.name == "Default" else profile.name
                self.lbl_selected_profile_name.setText(label)
            if hasattr(self, "edit_app_matches"):
                self.edit_app_matches.setText(", ".join(profile.app_matches))
                self.edit_app_matches.setEnabled(profile.name != "Default")
            if hasattr(self, "btn_del_prof"):
                self.btn_del_prof.setEnabled(profile.name != "Default")

            # 1. Click on touch
            if hasattr(self, "chk_click_on_touch"):
                self.chk_click_on_touch.setChecked(profile.click_on_touch)

            # 2. Buttons
            if hasattr(self, "combo_btn_prim"):
                for i in range(self.combo_btn_prim.count()):
                    if self.combo_btn_prim.itemData(i) == profile.button_primary:
                        self.combo_btn_prim.setCurrentIndex(i)
                        break
            if hasattr(self, "combo_btn_sec"):
                for i in range(self.combo_btn_sec.count()):
                    if self.combo_btn_sec.itemData(i) == profile.button_secondary:
                        self.combo_btn_sec.setCurrentIndex(i)
                        break

            # 3. Smoothing
            if hasattr(self, "slider_smooth"):
                self.slider_smooth.setValue(int(profile.stroke_smoothing * 100))
                self.lbl_smooth_val.setText(f"{int(profile.stroke_smoothing * 100)}%")

            # 4. Pressure sensitivity
            if hasattr(self, "preset_btn_group"):
                curve_type = profile.pressure_curve_type
                gamma = profile.pressure_gamma
                preset_matched = False
                for btn in self.preset_btn_group.buttons():
                    first_word = btn.text().split()[0].lower()
                    if first_word in ("soft", "firm", "sigmoid", "linear") and first_word == curve_type:
                        btn.setChecked(True)
                        preset_matched = True
                        break
                if not preset_matched:
                    checked_btn = self.preset_btn_group.checkedButton()
                    if checked_btn:
                        self.preset_btn_group.setExclusive(False)
                        checked_btn.setChecked(False)
                        self.preset_btn_group.setExclusive(True)

                self.slider_gamma.setValue(int(gamma * 100))
                self.lbl_gamma_val.setText(f"{gamma:.2f}")
                self.slider_min.setValue(int(profile.pressure_min * 100))
                self.lbl_min_val.setText(f"{int(profile.pressure_min * 100)}%")
                self.slider_max.setValue(int(profile.pressure_max * 100))
                self.lbl_max_val.setText(f"{int(profile.pressure_max * 100)}%")
                self._sync_curve_widget()

            # 5. Mapping
            if hasattr(self, "rb_map_all"):
                if profile.mapping_mode == "all":
                    self.rb_map_all.setChecked(True)
                elif profile.mapping_mode == "monitor":
                    self.rb_map_mon.setChecked(True)
                elif profile.mapping_mode == "custom":
                    self.rb_map_custom.setChecked(True)

                for i in range(self.combo_monitors.count()):
                    if self.combo_monitors.itemData(i) == profile.selected_monitor:
                        self.combo_monitors.setCurrentIndex(i)
                        break
                if len(profile.custom_bounds) == 4:
                    self.spin_cust_x.setValue(profile.custom_bounds[0])
                    self.spin_cust_y.setValue(profile.custom_bounds[1])
                    self.spin_cust_w.setValue(profile.custom_bounds[2])
                    self.spin_cust_h.setValue(profile.custom_bounds[3])

                idx = 1 if profile.device_mode == "tablet" else 0
                self.combo_dev_mode.setCurrentIndex(idx)

            # Sync live tablet
            self._update_monitor_widget()
            self._sync_tablet_mapping()
            self.worker.set_device_mode(mode=profile.device_mode)
            self.worker.update_tablet_settings(
                click_on_touch=profile.click_on_touch,
                pressure_curve_type=profile.pressure_curve_type,
                pressure_gamma=profile.pressure_gamma,
                pressure_min=profile.pressure_min,
                pressure_max=profile.pressure_max,
                stroke_smoothing=profile.stroke_smoothing,
                button_primary=profile.button_primary,
                button_secondary=profile.button_secondary,
            )
        finally:
            self._loading_profile = False

    # ------------------------------------------------------------------
    # TAB 1: Pen & Stylus Controls
    # ------------------------------------------------------------------
    def _create_pen_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Left Column: Tip Clicking, Hardware Buttons, Smoothing
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # 1. Pen Tip Contact & Clicking Group
        tip_group = QGroupBox("Pen Tip Contact && Clicking")
        tg_layout = QVBoxLayout(tip_group)
        tg_layout.setSpacing(8)

        self.chk_click_on_touch = QCheckBox("Enable Click on Touch (Pen contact generates mouse clicks / touch events)")
        self.chk_click_on_touch.setChecked(self.config.click_on_touch)
        self.chk_click_on_touch.toggled.connect(self._on_click_on_touch_toggled)
        tg_layout.addWidget(self.chk_click_on_touch)

        tip_desc = QLabel(
            "When disabled, hovering, movement, and pressure are tracked without emitting mouse click "
            "events. This allows gliding the stylus on screen without unintended clicks—ideal for keyboard-tapping "
            "rhythm games, custom gesture controls, or hover-only navigation."
        )
        tip_desc.setWordWrap(True)
        tip_desc.setStyleSheet("color: #a6adc8; font-size: 11px; line-height: 1.3;")
        tg_layout.addWidget(tip_desc)
        left_layout.addWidget(tip_group)

        # 2. Hardware Stylus Buttons
        btn_group = QGroupBox("Stylus Hardware Buttons")
        bg_layout = QGridLayout(btn_group)
        bg_layout.setSpacing(10)

        bg_layout.addWidget(QLabel("Primary Button (Side Barrel):"), 0, 0)
        self.combo_btn_prim = QComboBox()
        self.combo_btn_prim.addItem("Right Click (Default — Context Menu / Color Picker)", "right_click")
        self.combo_btn_prim.addItem("Middle Click (Pan / Rotate Canvas)", "middle_click")
        self.combo_btn_prim.addItem("Toggle Eraser Mode", "eraser")
        self.combo_btn_prim.addItem("Undo Shortcut (Ctrl+Z)", "undo")
        self.combo_btn_prim.addItem("Wacom Stylus Button (e.BTN_STYLUS)", "stylus")
        self.combo_btn_prim.addItem("Disabled", "none")

        for i in range(self.combo_btn_prim.count()):
            if self.combo_btn_prim.itemData(i) == self.config.button_primary:
                self.combo_btn_prim.setCurrentIndex(i)
                break
        self.combo_btn_prim.currentIndexChanged.connect(self._on_primary_btn_changed)
        bg_layout.addWidget(self.combo_btn_prim, 0, 1)

        bg_layout.addWidget(QLabel("Secondary Button:"), 1, 0)
        self.combo_btn_sec = QComboBox()
        self.combo_btn_sec.addItem("Middle Click (Default)", "middle_click")
        self.combo_btn_sec.addItem("Right Click", "right_click")
        self.combo_btn_sec.addItem("Toggle Eraser Mode", "eraser")
        self.combo_btn_sec.addItem("Undo Shortcut (Ctrl+Z)", "undo")
        self.combo_btn_sec.addItem("Wacom Stylus 2 (e.BTN_STYLUS2)", "stylus2")
        self.combo_btn_sec.addItem("Disabled", "none")

        for i in range(self.combo_btn_sec.count()):
            if self.combo_btn_sec.itemData(i) == self.config.button_secondary:
                self.combo_btn_sec.setCurrentIndex(i)
                break
        self.combo_btn_sec.currentIndexChanged.connect(self._on_secondary_btn_changed)
        bg_layout.addWidget(self.combo_btn_sec, 1, 1)
        left_layout.addWidget(btn_group)

        # 3. Stroke Smoothing
        smooth_group = QGroupBox("Stroke Smoothing && Jitter Reduction")
        sm_layout = QVBoxLayout(smooth_group)
        sm_layout.setSpacing(6)

        sm_header = QHBoxLayout()
        sm_header.addWidget(QLabel("Smoothing Filter Strength:"))
        self.lbl_smooth_val = QLabel(f"{int(self.config.stroke_smoothing * 100)}%")
        self.lbl_smooth_val.setStyleSheet("font-weight: bold; color: #a6e3a1;")
        sm_header.addWidget(self.lbl_smooth_val)
        sm_layout.addLayout(sm_header)

        self.slider_smooth = QSlider(Qt.Horizontal)
        self.slider_smooth.setRange(0, 85)
        self.slider_smooth.setValue(int(self.config.stroke_smoothing * 100))
        self.slider_smooth.valueChanged.connect(self._on_smooth_changed)
        sm_layout.addWidget(self.slider_smooth)

        sm_desc = QLabel("Filters coordinate noise and stabilizes lines for drawing or handwriting.")
        sm_desc.setStyleSheet("color: #a6adc8; font-size: 11px;")
        sm_layout.addWidget(sm_desc)
        left_layout.addWidget(smooth_group)

        left_layout.addStretch()
        layout.addWidget(left_box, stretch=5)

        # Right Column: Pressure Sensitivity & Transfer Function
        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        press_group = QGroupBox("Pressure Sensitivity Curve && Deadzone")
        pg_layout = QVBoxLayout(press_group)
        pg_layout.setSpacing(10)

        # Presets
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))
        presets = [
            ("Linear", "linear", 1.0),
            ("Soft", "soft", 0.65),
            ("Firm", "firm", 1.6),
            ("Sigmoid", "sigmoid", 1.0),
        ]
        self.preset_btn_group = QButtonGroup(self)
        for idx, (title, c_type, g_val) in enumerate(presets):
            btn = QPushButton(title)
            btn.setCheckable(True)
            if self.config.pressure_curve_type == c_type:
                btn.setChecked(True)
            btn.clicked.connect(lambda _, ct=c_type, g=g_val: self._apply_preset(ct, g))
            self.preset_btn_group.addButton(btn, idx)
            preset_row.addWidget(btn)
        pg_layout.addLayout(preset_row)

        # Sliders
        sliders_grid = QGridLayout()
        sliders_grid.setSpacing(6)

        # Sensitivity / Gamma
        sliders_grid.addWidget(QLabel("Sensitivity Exponent (Gamma):"), 0, 0)
        self.lbl_gamma_val = QLabel(f"{self.config.pressure_gamma:.2f}")
        self.lbl_gamma_val.setStyleSheet("font-weight: bold; color: #89b4fa;")
        sliders_grid.addWidget(self.lbl_gamma_val, 0, 1)

        self.slider_gamma = QSlider(Qt.Horizontal)
        self.slider_gamma.setRange(20, 300)
        self.slider_gamma.setValue(int(self.config.pressure_gamma * 100))
        self.slider_gamma.valueChanged.connect(self._on_gamma_changed)
        sliders_grid.addWidget(self.slider_gamma, 1, 0, 1, 2)

        # Minimum Threshold (Deadzone)
        sliders_grid.addWidget(QLabel("Minimum Pressure Threshold (Deadzone):"), 2, 0)
        self.lbl_min_val = QLabel(f"{int(self.config.pressure_min * 100)}%")
        self.lbl_min_val.setStyleSheet("font-weight: bold; color: #f38ba8;")
        sliders_grid.addWidget(self.lbl_min_val, 2, 1)

        self.slider_min = QSlider(Qt.Horizontal)
        self.slider_min.setRange(0, 30)
        self.slider_min.setValue(int(self.config.pressure_min * 100))
        self.slider_min.valueChanged.connect(self._on_min_changed)
        sliders_grid.addWidget(self.slider_min, 3, 0, 1, 2)

        # Maximum Force Ceiling
        sliders_grid.addWidget(QLabel("Maximum Pressure Ceiling (100% Force):"), 4, 0)
        self.lbl_max_val = QLabel(f"{int(self.config.pressure_max * 100)}%")
        self.lbl_max_val.setStyleSheet("font-weight: bold; color: #fab387;")
        sliders_grid.addWidget(self.lbl_max_val, 4, 1)

        self.slider_max = QSlider(Qt.Horizontal)
        self.slider_max.setRange(70, 100)
        self.slider_max.setValue(int(self.config.pressure_max * 100))
        self.slider_max.valueChanged.connect(self._on_max_changed)
        sliders_grid.addWidget(self.slider_max, 5, 0, 1, 2)

        pg_layout.addLayout(sliders_grid)

        # Live Curve Graph
        self.curve_widget = PressureCurveWidget()
        pg_layout.addWidget(self.curve_widget, stretch=1)

        # Live Pressure Meters
        meter_grid = QGridLayout()
        meter_grid.setSpacing(4)
        meter_grid.addWidget(QLabel("Raw Input:"), 0, 0)
        self.bar_raw = QProgressBar()
        self.bar_raw.setRange(0, 100)
        self.bar_raw.setValue(0)
        meter_grid.addWidget(self.bar_raw, 0, 1)

        meter_grid.addWidget(QLabel("Calibrated:"), 1, 0)
        self.bar_cal = QProgressBar()
        self.bar_cal.setRange(0, 100)
        self.bar_cal.setValue(0)
        meter_grid.addWidget(self.bar_cal, 1, 1)
        pg_layout.addLayout(meter_grid)

        right_layout.addWidget(press_group)
        layout.addWidget(right_box, stretch=6)

        self._sync_curve_widget()
        return widget

    # ------------------------------------------------------------------
    # TAB 2: Display & Area Mapping
    # ------------------------------------------------------------------
    def _create_mapping_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Left Column: Mapping Controls & Virtual Device Mode
        ctrl_box = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_box)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(12)

        # Mode Selection
        mode_group = QGroupBox("Screen Mapping Region")
        mg_layout = QVBoxLayout(mode_group)
        mg_layout.setSpacing(8)

        self.rb_map_all = QRadioButton("Full Virtual Desktop (Spanning all screens)")
        self.rb_map_all.setChecked(self.config.mapping_mode == "all")
        self.rb_map_all.toggled.connect(self._on_mapping_mode_changed)
        mg_layout.addWidget(self.rb_map_all)

        self.rb_map_mon = QRadioButton("Map to Specific Monitor:")
        self.rb_map_mon.setChecked(self.config.mapping_mode == "monitor")
        self.rb_map_mon.toggled.connect(self._on_mapping_mode_changed)
        mg_layout.addWidget(self.rb_map_mon)

        mon_select_row = QHBoxLayout()
        self.combo_monitors = QComboBox()
        self._populate_monitor_combo()
        self.combo_monitors.currentIndexChanged.connect(self._on_monitor_combo_changed)
        mon_select_row.addWidget(self.combo_monitors, stretch=1)

        btn_refresh_mon = QPushButton("Refresh")
        btn_refresh_mon.clicked.connect(self._refresh_monitors)
        mon_select_row.addWidget(btn_refresh_mon)
        mg_layout.addLayout(mon_select_row)

        self.rb_map_custom = QRadioButton("Custom Screen Rectangle (X, Y, W, H):")
        self.rb_map_custom.setChecked(self.config.mapping_mode == "custom")
        self.rb_map_custom.toggled.connect(self._on_mapping_mode_changed)
        mg_layout.addWidget(self.rb_map_custom)

        custom_grid = QGridLayout()
        custom_grid.addWidget(QLabel("X:"), 0, 0)
        self.spin_cust_x = QSpinBox()
        self.spin_cust_x.setRange(0, 10000)
        self.spin_cust_x.setValue(self.config.custom_bounds[0] if len(self.config.custom_bounds) > 0 else 0)
        self.spin_cust_x.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_x, 0, 1)

        custom_grid.addWidget(QLabel("Y:"), 0, 2)
        self.spin_cust_y = QSpinBox()
        self.spin_cust_y.setRange(0, 10000)
        self.spin_cust_y.setValue(self.config.custom_bounds[1] if len(self.config.custom_bounds) > 1 else 0)
        self.spin_cust_y.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_y, 0, 3)

        custom_grid.addWidget(QLabel("Width:"), 1, 0)
        self.spin_cust_w = QSpinBox()
        self.spin_cust_w.setRange(100, 10000)
        self.spin_cust_w.setValue(self.config.custom_bounds[2] if len(self.config.custom_bounds) > 2 else 1920)
        self.spin_cust_w.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_w, 1, 1)

        custom_grid.addWidget(QLabel("Height:"), 1, 2)
        self.spin_cust_h = QSpinBox()
        self.spin_cust_h.setRange(100, 10000)
        self.spin_cust_h.setValue(self.config.custom_bounds[3] if len(self.config.custom_bounds) > 3 else 1080)
        self.spin_cust_h.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_h, 1, 3)
        mg_layout.addLayout(custom_grid)

        ctrl_layout.addWidget(mode_group)

        # Aspect Ratio Lock
        ar_group = QGroupBox("Tablet Geometry && Aspect Ratio")
        ar_layout = QVBoxLayout(ar_group)
        ar_layout.setSpacing(8)

        self.chk_aspect_lock = QCheckBox("Lock Aspect Ratio (Prevents oval/distorted drawing)")
        self.chk_aspect_lock.setChecked(self.config.aspect_ratio_lock)
        self.chk_aspect_lock.toggled.connect(self._on_aspect_lock_changed)
        ar_layout.addWidget(self.chk_aspect_lock)

        ar_row = QHBoxLayout()
        ar_row.addWidget(QLabel("Tablet Screen Ratio:"))
        self.combo_aspect_ratio = QComboBox()
        self.combo_aspect_ratio.addItems(["16:10", "16:9", "4:3", "21:9", "3:2"])
        self.combo_aspect_ratio.setCurrentText(self.config.tablet_aspect_ratio)
        self.combo_aspect_ratio.currentTextChanged.connect(self._on_aspect_ratio_text_changed)
        ar_row.addWidget(self.combo_aspect_ratio)
        ar_layout.addLayout(ar_row)
        ctrl_layout.addWidget(ar_group)

        # Device Mode
        dev_group = QGroupBox("Virtual Device Mode")
        dev_layout = QVBoxLayout(dev_group)
        dev_layout.setSpacing(8)

        dev_mode_row = QHBoxLayout()
        dev_mode_row.addWidget(QLabel("Device Type:"))
        self.combo_dev_mode = QComboBox()
        self.combo_dev_mode.addItem("Pointer Mode (Absolute Cursor - Wayland & X11)", "pointer")
        self.combo_dev_mode.addItem("Tablet Mode (Wacom Tablet-v2 for Krita/GIMP)", "tablet")
        idx = 1 if self.config.device_mode == "tablet" else 0
        self.combo_dev_mode.setCurrentIndex(idx)
        self.combo_dev_mode.currentIndexChanged.connect(self._on_dev_mode_changed)
        dev_mode_row.addWidget(self.combo_dev_mode)
        dev_layout.addLayout(dev_mode_row)

        self.chk_direct_mode = QCheckBox("Enable INPUT_PROP_DIRECT (Display Tablet Mode)")
        self.chk_direct_mode.setChecked(self.config.direct_mode)
        self.chk_direct_mode.toggled.connect(self._on_direct_mode_changed)
        dev_layout.addWidget(self.chk_direct_mode)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Device Name:"))
        self.edit_dev_name = QLineEdit(self.config.device_name)
        self.edit_dev_name.textChanged.connect(lambda t: setattr(self.config, "device_name", t))
        name_row.addWidget(self.edit_dev_name)
        dev_layout.addLayout(name_row)

        ctrl_layout.addWidget(dev_group)
        ctrl_layout.addStretch()
        layout.addWidget(ctrl_box, stretch=5)

        # Right Column: Visual Monitor Arrangement
        map_box = QWidget()
        map_layout = QVBoxLayout(map_box)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(8)

        map_layout.addWidget(QLabel("<b>Visual Display Arrangement (Click to select target)</b>"))
        self.monitor_widget = MonitorLayoutWidget()
        self.monitor_widget.monitor_clicked.connect(self._on_monitor_clicked_on_map)
        map_layout.addWidget(self.monitor_widget, stretch=1)

        self.lbl_map_info = QLabel()
        self.lbl_map_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        map_layout.addWidget(self.lbl_map_info)

        layout.addWidget(map_box, stretch=5)

        self._update_monitor_widget()
        return widget

    # ------------------------------------------------------------------
    # TAB 3: Application Profiles
    # ------------------------------------------------------------------
    def _create_profiles_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Auto-Switch Bar & Live Window Indicator
        auto_group = QGroupBox("Automatic Profile Switching")
        ag_layout = QHBoxLayout(auto_group)
        ag_layout.setSpacing(14)

        self.chk_auto_switch = QCheckBox("Enable Automatic Switching based on focused window")
        self.chk_auto_switch.setChecked(self.config.auto_switch_profiles)
        self.chk_auto_switch.toggled.connect(self._on_auto_switch_toggled)
        ag_layout.addWidget(self.chk_auto_switch)

        ag_layout.addStretch()

        self.lbl_focused_window = QLabel("Active Window: <i>Detecting...</i>")
        self.lbl_focused_window.setStyleSheet("background: #181825; color: #89b4fa; padding: 4px 10px; border-radius: 6px; font-size: 12px;")
        ag_layout.addWidget(self.lbl_focused_window)
        layout.addWidget(auto_group)

        # Main Split: Profile List (Left) and Rules & Info (Right)
        body = QHBoxLayout()
        body.setSpacing(14)

        # Left Column: Profiles List
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(QLabel("<b>Configured Profiles:</b>"))

        self.profile_list_widget = QListWidget()
        self.profile_list_widget.currentItemChanged.connect(self._on_profile_list_selected)
        left_layout.addWidget(self.profile_list_widget, stretch=1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ New Profile")
        btn_add.clicked.connect(self._create_new_profile)
        btn_row.addWidget(btn_add)

        self.btn_del_prof = QPushButton("Delete")
        self.btn_del_prof.clicked.connect(self._delete_current_profile)
        btn_row.addWidget(self.btn_del_prof)
        left_layout.addLayout(btn_row)

        body.addWidget(left_box, stretch=4)

        # Right Column: Match Rules & Profile Overview
        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        rules_group = QGroupBox("Selected Profile Configuration")
        rg_layout = QVBoxLayout(rules_group)
        rg_layout.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Profile Name:"))
        self.lbl_selected_profile_name = QLabel("Default (Global Settings)")
        self.lbl_selected_profile_name.setStyleSheet("font-weight: bold; font-size: 14px; color: #cba6f7;")
        name_row.addWidget(self.lbl_selected_profile_name)
        name_row.addStretch()
        rg_layout.addLayout(name_row)

        rg_layout.addWidget(QLabel("Matching Application Window / Process Names:"))
        self.edit_app_matches = QLineEdit()
        self.edit_app_matches.setPlaceholderText("e.g. krita, blender, osu!, gimp")
        self.edit_app_matches.textChanged.connect(self._on_app_matches_edited)
        rg_layout.addWidget(self.edit_app_matches)

        match_hint = QLabel(
            "Enter comma-separated window class or process names. When any matching application is "
            "focused, this profile will activate automatically. Leave empty for profiles meant only for manual selection."
        )
        match_hint.setWordWrap(True)
        match_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        rg_layout.addWidget(match_hint)

        info_box = QGroupBox("Systematic Configuration Guide")
        ib_layout = QVBoxLayout(info_box)
        ib_layout.setSpacing(6)

        guide_text = QLabel(
            "<b>How Profiles Work:</b><br/>"
            "• <b>Default Profile</b> defines your global baseline settings across the entire system.<br/>"
            "• <b>Application Profiles</b> override specific settings when an application is active.<br/>"
            "• <b>Every Feature Is Configurable</b>: Selecting any profile in the top dropdown allows you to "
            "customize its Click on Touch, Stylus Buttons, Smoothing, Pressure Curve, and Screen Mapping in the "
            "<b>'Pen & Buttons'</b> and <b>'Display & Area'</b> tabs.<br/>"
            "• When switching profiles, all controls update immediately and the virtual tablet updates in real-time."
        )
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #cdd6f4; font-size: 12px; line-height: 1.4;")
        ib_layout.addWidget(guide_text)
        rg_layout.addWidget(info_box)

        rg_layout.addStretch()
        right_layout.addWidget(rules_group)
        body.addWidget(right_box, stretch=6)

        layout.addLayout(body)
        return widget

    # ------------------------------------------------------------------
    # TAB 4: Connection & Diagnostics
    # ------------------------------------------------------------------
    def _create_connection_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Left Column: Connect Info & Server/System Settings
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Quick Connect
        conn_group = QGroupBox("Quick Connect (Tablet Setup)")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(6)

        ip_info = QHBoxLayout()
        self.lbl_ip_info = QLabel(f"IP: <b>{self.local_ip}</b>   Port: <b>{self.config.port}</b>")
        self.lbl_ip_info.setStyleSheet("font-size: 13px;")
        ip_info.addWidget(self.lbl_ip_info)

        btn_copy_ip = QPushButton("Copy")
        btn_copy_ip.setMaximumWidth(70)
        btn_copy_ip.clicked.connect(self._copy_connection_info)
        ip_info.addWidget(btn_copy_ip)
        conn_layout.addLayout(ip_info)

        # QR Code Mode Selector
        qr_mode_layout = QHBoxLayout()
        self.rb_qr_apk = QRadioButton("Download APK")
        self.rb_qr_apk.setChecked(True)
        self.rb_qr_apk.toggled.connect(self._update_qr_code)
        self.rb_qr_conn = QRadioButton("Direct Connect")
        self.rb_qr_conn.toggled.connect(self._update_qr_code)
        qr_mode_layout.addWidget(self.rb_qr_apk)
        qr_mode_layout.addWidget(self.rb_qr_conn)
        conn_layout.addLayout(qr_mode_layout)

        # QR Code Image View
        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        self.lbl_qr.setMinimumSize(115, 115)
        self.lbl_qr.setStyleSheet("background: #ffffff; border-radius: 8px; padding: 4px;")
        conn_layout.addWidget(self.lbl_qr, alignment=Qt.AlignCenter)

        self.lbl_qr_hint = QLabel("Scan with tablet camera to download APK")
        self.lbl_qr_hint.setAlignment(Qt.AlignCenter)
        self.lbl_qr_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        conn_layout.addWidget(self.lbl_qr_hint)

        # USB ADB Button
        self.btn_adb = QPushButton("Forward USB Port (ADB)")
        self.btn_adb.setToolTip("Sets up ultra-low-latency 0ms USB cable connection via adb forward")
        self.btn_adb.clicked.connect(self.run_adb_forward)
        conn_layout.addWidget(self.btn_adb)

        left_layout.addWidget(conn_group)

        # System & Startup Preferences
        sys_group = QGroupBox("System && Startup Preferences")
        sg_layout = QGridLayout(sys_group)
        sg_layout.setSpacing(6)

        sg_layout.addWidget(QLabel("Port:"), 0, 0)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(self.config.port)
        self.spin_port.valueChanged.connect(self._on_port_changed)
        sg_layout.addWidget(self.spin_port, 0, 1)

        self.chk_autostart_server = QCheckBox("Auto-start server on app launch")
        self.chk_autostart_server.setChecked(self.config.auto_start_server)
        self.chk_autostart_server.toggled.connect(lambda c: setattr(self.config, "auto_start_server", c))
        sg_layout.addWidget(self.chk_autostart_server, 1, 0, 1, 2)

        self.chk_auto_adb = QCheckBox("Auto-forward USB ADB on launch")
        self.chk_auto_adb.setChecked(self.config.auto_adb_forward)
        self.chk_auto_adb.toggled.connect(lambda c: setattr(self.config, "auto_adb_forward", c))
        sg_layout.addWidget(self.chk_auto_adb, 2, 0, 1, 2)

        self.chk_tray = QCheckBox("Minimize to tray on window close")
        self.chk_tray.setChecked(self.config.minimize_to_tray)
        self.chk_tray.toggled.connect(lambda c: setattr(self.config, "minimize_to_tray", c))
        sg_layout.addWidget(self.chk_tray, 3, 0, 1, 2)

        btn_uinput = QPushButton("Check / Setup uinput Permissions")
        btn_uinput.clicked.connect(self._check_uinput_perms)
        sg_layout.addWidget(btn_uinput, 4, 0, 1, 2)

        btn_desktop_entry = QPushButton("Install Desktop Launcher (.desktop)")
        btn_desktop_entry.clicked.connect(self._install_desktop_entry)
        sg_layout.addWidget(btn_desktop_entry, 5, 0, 1, 2)

        btn_reset = QPushButton("Reset All to Defaults")
        btn_reset.clicked.connect(self._reset_defaults)
        sg_layout.addWidget(btn_reset, 6, 0, 1, 2)

        left_layout.addWidget(sys_group)
        left_layout.addStretch()
        layout.addWidget(left_box, stretch=4)

        # Right Column: Diagnostics & Scratchpad & Logs
        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Live S Pen Diagnostics Card
        diag_group = QGroupBox("Live S Pen Input Diagnostics")
        diag_layout = QVBoxLayout(diag_group)
        diag_layout.setSpacing(6)

        self.lbl_pressure_diag = QLabel("Pressure: 0 / 4095 (0%)")
        diag_layout.addWidget(self.lbl_pressure_diag)

        self.bar_pressure = QProgressBar()
        self.bar_pressure.setRange(0, 4095)
        self.bar_pressure.setValue(0)
        diag_layout.addWidget(self.bar_pressure)

        coords_layout = QGridLayout()
        coords_layout.addWidget(QLabel("Position:"), 0, 0)
        self.lbl_pos_val = QLabel("0.000, 0.000")
        self.lbl_pos_val.setStyleSheet("font-weight: bold; color: #89b4fa;")
        coords_layout.addWidget(self.lbl_pos_val, 0, 1)

        coords_layout.addWidget(QLabel("Tilt:"), 0, 2)
        self.lbl_tilt_val = QLabel("0.0°, 0.0°")
        coords_layout.addWidget(self.lbl_tilt_val, 0, 3)

        coords_layout.addWidget(QLabel("Traffic:"), 1, 0)
        self.lbl_traffic_val = QLabel("0 events/sec")
        coords_layout.addWidget(self.lbl_traffic_val, 1, 1)
        diag_layout.addLayout(coords_layout)

        badges_layout = QHBoxLayout()
        self.badge_hover = QLabel("Hover")
        self.badge_hover.setStyleSheet("background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        self.badge_touch = QLabel("Touch")
        self.badge_touch.setStyleSheet("background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        self.badge_barrel = QLabel("Barrel Btn")
        self.badge_barrel.setStyleSheet("background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        self.badge_eraser = QLabel("Eraser")
        self.badge_eraser.setStyleSheet("background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        self.badge_click = QLabel("Click: ON")
        self.badge_click.setStyleSheet("background: #a6e3a1; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px; font-size: 11px;")

        badges_layout.addWidget(self.badge_hover)
        badges_layout.addWidget(self.badge_touch)
        badges_layout.addWidget(self.badge_barrel)
        badges_layout.addWidget(self.badge_eraser)
        badges_layout.addWidget(self.badge_click)
        diag_layout.addLayout(badges_layout)

        right_layout.addWidget(diag_group)

        # Drawing Scratchpad Card
        scratch_group = QGroupBox("Interactive Scratchpad")
        scratch_layout = QVBoxLayout(scratch_group)
        scratch_layout.setSpacing(6)

        scratchpad_header = QHBoxLayout()
        for col_hex in ["#89b4fa", "#cba6f7", "#a6e3a1", "#f9e2af", "#f38ba8", "#ffffff"]:
            btn_col = QPushButton()
            btn_col.setFixedSize(18, 18)
            btn_col.setStyleSheet(f"background-color: {col_hex}; border-radius: 9px; border: 1px solid #585b70;")
            btn_col.clicked.connect(lambda _, c=col_hex: self.scratchpad.set_pen_color(QColor(c)))
            scratchpad_header.addWidget(btn_col)

        scratchpad_header.addStretch()
        btn_synthetic = QPushButton("Test Stroke")
        btn_synthetic.clicked.connect(self._run_synthetic_test)
        scratchpad_header.addWidget(btn_synthetic)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.scratchpad.clear_canvas())
        scratchpad_header.addWidget(btn_clear)
        scratch_layout.addLayout(scratchpad_header)

        self.scratchpad = ScratchpadWidget()
        self.scratchpad.setMinimumHeight(120)
        scratch_layout.addWidget(self.scratchpad, stretch=1)
        right_layout.addWidget(scratch_group, stretch=1)

        # Server Logs
        log_group = QGroupBox("Server Logs")
        lg_layout = QVBoxLayout(log_group)
        lg_layout.setSpacing(4)

        log_h = QHBoxLayout()
        log_h.addStretch()
        btn_copy_logs = QPushButton("Copy")
        btn_copy_logs.clicked.connect(lambda: QApplication.clipboard().setText(self.text_logs.toPlainText()))
        log_h.addWidget(btn_copy_logs)
        btn_clear_logs = QPushButton("Clear")
        btn_clear_logs.clicked.connect(lambda: self.text_logs.clear())
        log_h.addWidget(btn_clear_logs)
        lg_layout.addLayout(log_h)

        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        self.text_logs.setMaximumHeight(90)
        lg_layout.addWidget(self.text_logs)
        right_layout.addWidget(log_group)

        layout.addWidget(right_box, stretch=6)

        self._update_qr_code()
        return widget

    def _update_qr_code(self):
        if self.rb_qr_apk.isChecked():
            data = f"http://{self.local_ip}:8080/spen-on-linux.apk"
            self.lbl_qr_hint.setText(f"Scan to download APK (http://{self.local_ip}:8080)")
        else:
            data = f"spen://{self.local_ip}:{self.config.port}"
            self.lbl_qr_hint.setText(f"Server Target: {self.local_ip}:{self.config.port}")

        qr = qrcode.QRCode(box_size=3, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#11111b", back_color="#ffffff").convert("RGB")
        data_bytes = img.tobytes("raw", "RGB")
        qimg = QImage(data_bytes, img.size[0], img.size[1], QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(115, 115, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_qr.setPixmap(pix)

    def _copy_connection_info(self):
        text = f"{self.local_ip}:{self.config.port}"
        QApplication.clipboard().setText(text)
        self.lbl_ip_info.setText(f"IP: <b>{self.local_ip}</b>  (Copied!)")
        QTimer.singleShot(1500, lambda: self.lbl_ip_info.setText(f"IP: <b>{self.local_ip}</b>   Port: <b>{self.config.port}</b>"))

    def _populate_monitor_combo(self):
        self.combo_monitors.blockSignals(True)
        self.combo_monitors.clear()
        for mon in self.monitors:
            label = f"{mon['name']} ({mon['width']}x{mon['height']} at +{mon['x']}+{mon['y']})"
            self.combo_monitors.addItem(label, mon['name'])
            if mon['name'] == self.config.selected_monitor:
                self.combo_monitors.setCurrentIndex(self.combo_monitors.count() - 1)
        self.combo_monitors.blockSignals(False)

    def _refresh_monitors(self):
        self.monitors, self.desktop_size = detect_monitors()
        self.config.desktop_size = [self.desktop_size[0], self.desktop_size[1]]
        self._populate_monitor_combo()
        self._update_monitor_widget()
        self._sync_tablet_mapping()

    def _on_mapping_mode_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        if self.rb_map_all.isChecked():
            self.config.mapping_mode = "all"
        elif self.rb_map_mon.isChecked():
            self.config.mapping_mode = "monitor"
        elif self.rb_map_custom.isChecked():
            self.config.mapping_mode = "custom"
        self._update_monitor_widget()
        self._sync_tablet_mapping()

    def _on_monitor_combo_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        cur_name = self.combo_monitors.currentData()
        if cur_name:
            self.config.selected_monitor = cur_name
            self.rb_map_mon.setChecked(True)
            self._update_monitor_widget()
            self._sync_tablet_mapping()

    def _on_monitor_clicked_on_map(self, monitor_name: str):
        if getattr(self, "_loading_profile", False):
            return
        self.config.selected_monitor = monitor_name
        self.config.mapping_mode = "monitor"
        self.rb_map_mon.setChecked(True)
        for i in range(self.combo_monitors.count()):
            if self.combo_monitors.itemData(i) == monitor_name:
                self.combo_monitors.setCurrentIndex(i)
                break
        self._update_monitor_widget()
        self._sync_tablet_mapping()

    def _on_custom_bounds_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        self.config.custom_bounds = [
            self.spin_cust_x.value(),
            self.spin_cust_y.value(),
            self.spin_cust_w.value(),
            self.spin_cust_h.value(),
        ]
        self._update_monitor_widget()
        self._sync_tablet_mapping()

    def _on_aspect_lock_changed(self, checked: bool):
        if getattr(self, "_loading_profile", False):
            return
        self.config.aspect_ratio_lock = checked
        self.worker.update_tablet_settings(aspect_ratio_lock=checked)

    def _on_aspect_ratio_text_changed(self, text: str):
        if getattr(self, "_loading_profile", False):
            return
        self.config.tablet_aspect_ratio = text
        self.worker.update_tablet_settings(tablet_aspect_ratio=text)

    def _on_dev_mode_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        mode = self.combo_dev_mode.currentData()
        self.config.device_mode = mode
        self.worker.set_device_mode(mode=mode)
        self.log(f"Device mode changed to: {mode}")

    def _on_direct_mode_changed(self, checked: bool):
        if getattr(self, "_loading_profile", False):
            return
        self.config.direct_mode = checked
        self.worker.set_device_mode(direct_mode=checked)
        self.log(f"Direct mode changed to: {checked}")

    def _update_monitor_widget(self):
        self.monitor_widget.set_data(
            monitors=self.monitors,
            desktop_size=self.desktop_size,
            mapping_mode=self.config.mapping_mode,
            selected_monitor=self.config.selected_monitor,
            custom_bounds=tuple(self.config.custom_bounds),
        )
        total_w, total_h = self.desktop_size
        if self.config.mapping_mode == "all":
            desc = f"Active Area: Entire Virtual Desktop ({total_w}x{total_h})"
        elif self.config.mapping_mode == "monitor":
            desc = f"Active Area: Single Monitor ({self.config.selected_monitor})"
        else:
            cb = self.config.custom_bounds
            desc = f"Active Area: Custom Rect ({cb[0]},{cb[1]} {cb[2]}x{cb[3]})"
        self.lbl_map_info.setText(desc)

    def _sync_tablet_mapping(self):
        sb, desk = self.config.get_screen_bounds_and_desktop(self.monitors)
        self.worker.update_tablet_settings(screen_bounds=sb, desktop_size=desk)

    def _apply_preset(self, curve_type: str, gamma: float):
        if getattr(self, "_loading_profile", False):
            return
        self.config.pressure_curve_type = curve_type
        self.config.pressure_gamma = gamma
        self.slider_gamma.setValue(int(gamma * 100))
        self.lbl_gamma_val.setText(f"{gamma:.2f}")
        self._sync_curve_widget()
        self.worker.update_tablet_settings(
            pressure_curve_type=curve_type,
            pressure_gamma=gamma,
        )

    def _on_gamma_changed(self, val: int):
        if getattr(self, "_loading_profile", False):
            return
        gamma = val / 100.0
        self.config.pressure_gamma = gamma
        self.config.pressure_curve_type = "custom"
        self.lbl_gamma_val.setText(f"{gamma:.2f}")
        self._sync_curve_widget()
        self.worker.update_tablet_settings(
            pressure_curve_type="custom",
            pressure_gamma=gamma,
        )

    def _on_min_changed(self, val: int):
        if getattr(self, "_loading_profile", False):
            return
        p_min = val / 100.0
        self.config.pressure_min = p_min
        self.lbl_min_val.setText(f"{val}%")
        self._sync_curve_widget()
        self.worker.update_tablet_settings(pressure_min=p_min)

    def _on_max_changed(self, val: int):
        if getattr(self, "_loading_profile", False):
            return
        p_max = val / 100.0
        self.config.pressure_max = p_max
        self.lbl_max_val.setText(f"{val}%")
        self._sync_curve_widget()
        self.worker.update_tablet_settings(pressure_max=p_max)

    def _on_smooth_changed(self, val: int):
        if getattr(self, "_loading_profile", False):
            return
        smooth = val / 100.0
        self.config.stroke_smoothing = smooth
        self.lbl_smooth_val.setText(f"{val}%")
        self.worker.update_tablet_settings(stroke_smoothing=smooth)

    def _sync_curve_widget(self):
        self.curve_widget.set_params(
            curve_type=self.config.pressure_curve_type,
            gamma=self.config.pressure_gamma,
            p_min=self.config.pressure_min,
            p_max=self.config.pressure_max,
        )

    def _on_primary_btn_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        act = self.combo_btn_prim.currentData()
        self.config.button_primary = act
        self.worker.update_tablet_settings(button_primary=act)

    def _on_secondary_btn_changed(self):
        if getattr(self, "_loading_profile", False):
            return
        act = self.combo_btn_sec.currentData()
        self.config.button_secondary = act
        self.worker.update_tablet_settings(button_secondary=act)

    def _on_port_changed(self, val: int):
        self.config.port = val
        self._update_qr_code()
        self.lbl_ip_info.setText(f"IP: <b>{self.local_ip}</b>   Port: <b>{self.config.port}</b>")

    def _check_uinput_perms(self):
        uinput_path = Path("/dev/uinput")
        if uinput_path.exists() and os.access(uinput_path, os.W_OK):
            QMessageBox.information(
                self,
                "uinput Check",
                "/dev/uinput is writable!\nYour user has full permissions to create virtual graphics tablets.",
            )
        else:
            ans = QMessageBox.question(
                self,
                "uinput Setup Needed",
                "/dev/uinput is not writable by current user.\nWould you like to run ./server/setup_uinput.sh now?",
            )
            if ans == QMessageBox.Yes:
                setup_script = REPO_ROOT / "server" / "setup_uinput.sh"
                subprocess.Popen(["bash", str(setup_script)])

    def _install_desktop_entry(self):
        """Create and install .desktop file for system application launcher."""
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = apps_dir / "spen-on-linux.desktop"

        content = f"""[Desktop Entry]
Name=S Pen on Linux
Comment=Turn Samsung Galaxy Tab & S Pen into a Linux graphics tablet
Exec={REPO_ROOT}/server/.venv/bin/python {REPO_ROOT}/server/main.py --gui
Icon={REPO_ROOT}/qr_spen.png
Terminal=false
Type=Application
Categories=Graphics;Utility;
Keywords=spen;tablet;wacom;stylus;samsung;
"""
        try:
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            desktop_file.chmod(0o755)
            QMessageBox.information(
                self,
                "Desktop Launcher Installed",
                f"Application menu entry created:\n{desktop_file}\n\nYou can now launch 'S Pen on Linux' from your app menu / launcher!",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install desktop launcher: {e}")

    def _reset_defaults(self):
        ans = QMessageBox.question(
            self,
            "Reset Defaults",
            "Reset all tablet settings to default values?",
        )
        if ans == QMessageBox.Yes:
            self.config = TabletConfig()
            save_config(self.config)
            self._populate_profile_combo()
            self._load_profile_into_ui(self.config.get_active_profile())
            QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.text_logs.append(f"[{timestamp}] {message}")

    # ------------------------------------------------------------------
    # Server Control & ADB Actions
    # ------------------------------------------------------------------
    def toggle_server(self):
        if self.worker._is_running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        self.log(f"Starting server on {self.config.host}:{self.config.port}...")
        self.btn_server_toggle.setText("Starting...")
        self.btn_server_toggle.setEnabled(False)
        self.worker.start_server()

    def stop_server(self):
        self.log("Stopping server...")
        self.btn_server_toggle.setText("Stopping...")
        self.btn_server_toggle.setEnabled(False)
        self.worker.stop_server()

    def run_adb_forward(self):
        self.log("Running 'adb forward tcp:40118 tcp:40118'...")
        try:
            res = subprocess.run(
                ["adb", "forward", f"tcp:{self.config.port}", f"tcp:{self.config.port}"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                self.log("ADB forward successful! USB Mode ready.")
                self.btn_adb.setText("USB Active (ADB)")
                self.btn_adb.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
            else:
                err = res.stderr.strip() or "No device found"
                self.log(f"ADB forward failed: {err}")
                QMessageBox.warning(
                    self,
                    "ADB Forward",
                    f"ADB forward returned error:\n{err}\n\nMake sure your tablet is connected via USB and USB Debugging is enabled.",
                )
        except FileNotFoundError:
            self.log("ADB command not found.")
            QMessageBox.warning(
                self,
                "ADB Missing",
                "adb is not installed on this system.\nInstall with: sudo pacman -S android-tools (or sudo apt install adb)",
            )
        except Exception as e:
            self.log(f"ADB forward error: {e}")

    def save_all_settings(self):
        if save_config(self.config):
            self.log("Configuration saved successfully.")
            QMessageBox.information(self, "Saved", f"Settings saved to:\n{CONFIG_FILE_PATH}")
        else:
            QMessageBox.warning(self, "Error", "Failed to save configuration file.")

    def _run_synthetic_test(self):
        """Draw test spiral on scratchpad and trigger server stroke."""
        self.scratchpad.draw_test_spiral()

        # Also run synthetic network test in background if server is running
        if self.worker._is_running:
            threading.Thread(
                target=self._send_synthetic_network_stroke,
                daemon=True,
            ).start()

    def _send_synthetic_network_stroke(self):
        try:
            from server.test_synthetic import run_synthetic_network_test
            run_synthetic_network_test(host="127.0.0.1", port=self.config.port, count=1)
        except Exception as e:
            logger.debug(f"Synthetic test error: {e}")

    # ------------------------------------------------------------------
    # Server Callbacks
    # ------------------------------------------------------------------
    @Slot(str, str)
    def on_server_status(self, status: str, message: str):
        self.log(f"Server Status: {status} ({message})")
        self.btn_server_toggle.setEnabled(True)

        if status == "running":
            self.status_badge.setText(f"● Listening (Port {self.config.port})")
            self.status_badge.setStyleSheet("""
                background-color: #313244;
                color: #f9e2af;
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 12px;
            """)
            self.btn_server_toggle.setText("Stop Server")
            self.btn_server_toggle.setObjectName("dangerBtn")
        elif status == "stopped":
            self.status_badge.setText("● Server Stopped")
            self.status_badge.setStyleSheet("""
                background-color: #313244;
                color: #f38ba8;
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 12px;
            """)
            self.btn_server_toggle.setText("Start Server")
            self.btn_server_toggle.setObjectName("successBtn")
        elif status == "error":
            self.status_badge.setText("● Error")
            self.btn_server_toggle.setText("Retry Start")
            self.btn_server_toggle.setObjectName("primaryBtn")
            QMessageBox.critical(self, "Server Error", message)

        self._apply_dark_style()

    @Slot(str)
    def on_client_connected(self, client_addr: str):
        self.log(f"Tablet connected from {client_addr}")
        self.status_badge.setText(f"● Connected: {client_addr}")
        self.status_badge.setStyleSheet("""
            background-color: #313244;
            color: #a6e3a1;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 12px;
        """)
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage("S Pen Connected", f"Tablet connected from {client_addr}", QSystemTrayIcon.Information, 2000)

    @Slot(str)
    def on_client_disconnected(self, client_addr: str):
        self.log(f"Tablet disconnected: {client_addr}")
        if self.worker._is_running:
            self.status_badge.setText(f"● Listening (Port {self.config.port})")
            self.status_badge.setStyleSheet("""
                background-color: #313244;
                color: #f9e2af;
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 12px;
            """)

    @Slot(float, int, int)
    def on_server_stats(self, rate: float, packets: int, total_events: int):
        self.lbl_traffic_val.setText(f"{rate:.1f} events/sec ({packets} pkts)")

    @Slot(object, int, int, int)
    def on_pen_event(self, ev: PenEvent, cal_p: int, abs_x: int, abs_y: int):
        # Cache for 30 FPS timer update
        self._latest_pen_event = ev
        self._latest_cal_p = cal_p
        self._latest_abs_x = abs_x
        self._latest_abs_y = abs_y

        # Forward stroke to scratchpad
        self.scratchpad.add_tablet_point(ev.x, ev.y, cal_p / 4095.0, ev.action)

    def update_live_diagnostics(self):
        if self._latest_pen_event is None:
            return

        ev = self._latest_pen_event
        cal_p = self._latest_cal_p
        abs_x = self._latest_abs_x
        abs_y = self._latest_abs_y

        pct = int((cal_p / 4095.0) * 100)
        self.bar_pressure.setValue(cal_p)
        self.lbl_pressure_diag.setText(f"Pressure: {cal_p} / 4095 ({pct}%)")

        self.lbl_pos_val.setText(f"{ev.x:.3f}, {ev.y:.3f}  ({abs_x}, {abs_y})")
        self.lbl_tilt_val.setText(f"{ev.tilt_x:.1f}°, {ev.tilt_y:.1f}°")

        # Update curve live indicator ball
        self.curve_widget.set_current_pressure(ev.pressure, cal_p / 4095.0)
        self.bar_raw.setValue(int(ev.pressure * 100))
        self.bar_cal.setValue(pct)

        # Status badges
        is_hover = (ev.action in (0, 1))
        is_down = (ev.action in (3, 4))
        has_barrel = bool(ev.buttons & 1)

        self.badge_hover.setStyleSheet(
            "background: #89b4fa; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px;"
            if is_hover else
            "background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px;"
        )
        self.badge_touch.setStyleSheet(
            "background: #a6e3a1; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px;"
            if is_down else
            "background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px;"
        )
        self.badge_barrel.setStyleSheet(
            "background: #fab387; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px;"
            if has_barrel else
            "background: #313244; color: #6c7086; padding: 3px 6px; border-radius: 4px;"
        )

        # Click on touch indicator badge
        if self.config.click_on_touch:
            self.badge_click.setText("Click: ON")
            self.badge_click.setStyleSheet("background: #a6e3a1; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px; font-size: 11px;")
        else:
            self.badge_click.setText("Click: OFF")
            self.badge_click.setStyleSheet("background: #f38ba8; color: #11111b; font-weight: bold; padding: 3px 6px; border-radius: 4px; font-size: 11px;")

    # ------------------------------------------------------------------
    # System Tray Integration
    # ------------------------------------------------------------------
    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = REPO_ROOT / "spen_icon.png"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        act_show = tray_menu.addAction("Show Dashboard")
        act_show.triggered.connect(self.show_and_activate)

        tray_menu.addSeparator()

        self.act_tray_toggle = tray_menu.addAction("Start Server")
        self.act_tray_toggle.triggered.connect(self.toggle_server)

        tray_menu.addSeparator()

        act_quit = tray_menu.addAction("Quit")
        act_quit.triggered.connect(self.force_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_and_activate()

    def show_and_activate(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.config.minimize_to_tray and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage("S Pen on Linux", "Application minimized to system tray.", QSystemTrayIcon.Information, 1500)
        else:
            self.force_quit()

    def force_quit(self):
        self.worker.stop_server()
        self.http_server.stop()
        QApplication.quit()


# ----------------------------------------------------------------------
# Application Entry Point
# ----------------------------------------------------------------------
def launch_gui():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("S Pen on Linux")
    app.setOrganizationName("SPenOnLinux")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
