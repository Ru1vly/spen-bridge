"""
Quick Connect panel: LAN IP + port display (enter these in the Android app's
Settings screen) and the USB/ADB low-latency forwarding shortcut.
"""

import logging
import subprocess
import sys

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QApplication,
)

from server.config import TabletConfig

logger = logging.getLogger("SPenGUI")


class ConnectionPanel(QGroupBox):
    log_message = Signal(str)

    def __init__(self, local_ip: str, config: TabletConfig, parent=None):
        super().__init__("Quick Connect (Tablet Setup)", parent)
        self._local_ip = local_ip
        self._config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        ip_row = QHBoxLayout()
        self.lbl_ip_info = QLabel()
        ip_row.addWidget(self.lbl_ip_info)
        btn_copy_ip = QPushButton("Copy")
        btn_copy_ip.setMaximumWidth(70)
        btn_copy_ip.clicked.connect(self._copy_connection_info)
        ip_row.addWidget(btn_copy_ip)
        layout.addLayout(ip_row)

        self.lbl_hint = QLabel("Enter this IP and port in the tablet app's Settings screen.")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        self.btn_adb = QPushButton("Enable USB Mode (ADB)")
        self.btn_adb.setToolTip("Sets up an ultra-low-latency USB cable connection via adb reverse")
        self.btn_adb.clicked.connect(self.run_adb_reverse)
        layout.addWidget(self.btn_adb)

        self.refresh_ip_label()

    def refresh_ip_label(self):
        self.lbl_ip_info.setText(f"IP: <b>{self._local_ip}</b>   Port: <b>{self._config.port}</b>")

    def on_port_changed(self, port: int):
        self.refresh_ip_label()

    def _copy_connection_info(self):
        text = f"{self._local_ip}:{self._config.port}"
        QApplication.clipboard().setText(text)
        self.lbl_ip_info.setText(f"IP: <b>{self._local_ip}</b>  (Copied!)")
        QTimer.singleShot(1500, self.refresh_ip_label)

    def run_adb_reverse(self, silent: bool = False):
        # The Android app in USB mode is told to connect to 127.0.0.1:{port}
        # (i.e. "localhost" from the DEVICE's perspective), while the desktop
        # server listens on {port} on the HOST. `adb reverse` is what tunnels
        # a connection made TO a port ON THE DEVICE to a port ON THE HOST -
        # `adb forward` does the opposite (host listens, tunnels to device)
        # and previously made this button fail outright, since it tried to
        # bind the same host port the Python server already owns.
        self.log_message.emit(f"Running 'adb reverse tcp:{self._config.port} tcp:{self._config.port}'...")
        try:
            res = subprocess.run(
                ["adb", "reverse", f"tcp:{self._config.port}", f"tcp:{self._config.port}"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                self.log_message.emit("ADB reverse successful! USB Mode ready.")
                self.btn_adb.setText("USB Active (ADB)")
                self.btn_adb.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
            else:
                err = res.stderr.strip() or "No device found"
                self.log_message.emit(f"ADB reverse failed: {err}")
                if not silent:
                    QMessageBox.warning(
                        self,
                        "ADB Reverse",
                        f"ADB reverse returned error:\n{err}\n\nMake sure your tablet is connected via USB and USB Debugging is enabled.",
                    )
        except FileNotFoundError:
            self.log_message.emit("ADB command not found.")
            if not silent:
                if sys.platform == "win32":
                    hint = "adb is not on your PATH.\nInstall Android Studio (or just the platform-tools ZIP) and add it to PATH."
                else:
                    hint = "adb is not installed on this system.\nInstall with: sudo pacman -S android-tools (or sudo apt install adb)"
                QMessageBox.warning(self, "ADB Missing", hint)
        except Exception as e:
            self.log_message.emit(f"ADB forward error: {e}")
