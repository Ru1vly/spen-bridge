"""
System & Startup Preferences panel: network port, startup toggles, device
identity, uinput permission check, desktop launcher installer, and the
global reset-to-defaults action.
"""

import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
)

from server.config import TabletConfig

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class StartupPanel(QGroupBox):
    port_changed = Signal(int)
    reset_requested = Signal()

    def __init__(self, config: TabletConfig, parent=None):
        super().__init__("System && Startup Preferences", parent)
        self._config = config
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(self.spin_port)
        port_row.addStretch()
        layout.addLayout(port_row)

        self.chk_autostart_server = QCheckBox("Auto-start server on app launch")
        self.chk_autostart_server.toggled.connect(lambda c: setattr(self._config, "auto_start_server", c))
        layout.addWidget(self.chk_autostart_server)

        self.chk_auto_adb = QCheckBox("Auto-forward USB ADB on launch")
        self.chk_auto_adb.toggled.connect(lambda c: setattr(self._config, "auto_adb_forward", c))
        layout.addWidget(self.chk_auto_adb)

        self.chk_tray = QCheckBox("Minimize to tray on window close")
        self.chk_tray.toggled.connect(lambda c: setattr(self._config, "minimize_to_tray", c))
        layout.addWidget(self.chk_tray)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Device Name:"))
        self.edit_dev_name = QLineEdit()
        self.edit_dev_name.textChanged.connect(lambda t: setattr(self._config, "device_name", t))
        name_row.addWidget(self.edit_dev_name)
        layout.addLayout(name_row)

        self.lbl_desktop_size = QLabel()
        self.lbl_desktop_size.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.lbl_desktop_size)

        # uinput permissions and the .desktop launcher are Linux-only concerns:
        # on Windows the driver is installed once by the installer (an elevated
        # step, not a per-launch check) and the Start Menu shortcut is created
        # by the installer too, so surfacing either button there would just be
        # confusing (or create a duplicate/conflicting launcher entry).
        if sys.platform != "win32":
            btn_uinput = QPushButton("Check / Setup uinput Permissions")
            btn_uinput.clicked.connect(self._check_uinput_perms)
            layout.addWidget(btn_uinput)

            btn_desktop_entry = QPushButton("Install Desktop Launcher (.desktop)")
            btn_desktop_entry.clicked.connect(self._install_desktop_entry)
            layout.addWidget(btn_desktop_entry)

        btn_reset = QPushButton("Reset All to Defaults")
        btn_reset.setObjectName("dangerBtn")
        btn_reset.setStyleSheet("margin-top: 12px;")
        btn_reset.clicked.connect(self.reset_requested.emit)
        layout.addWidget(btn_reset)

        self._sync_from_config()

    def _sync_from_config(self):
        self._updating = True
        try:
            self.spin_port.setValue(self._config.port)
            self.chk_autostart_server.setChecked(self._config.auto_start_server)
            self.chk_auto_adb.setChecked(self._config.auto_adb_forward)
            self.chk_tray.setChecked(self._config.minimize_to_tray)
            self.edit_dev_name.setText(self._config.device_name)
        finally:
            self._updating = False

    def set_desktop_size(self, size):
        self.lbl_desktop_size.setText(f"Detected desktop: {size[0]}x{size[1]}")

    def _on_port_changed(self, value: int):
        if self._updating:
            return
        self._config.port = value
        self.port_changed.emit(value)

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
        desktop_file = apps_dir / "spen-bridge.desktop"

        content = f"""[Desktop Entry]
Name=S Pen Bridge
Comment=Turn Samsung Galaxy Tab & S Pen into a Linux graphics tablet
Exec={REPO_ROOT}/server/.venv/bin/python {REPO_ROOT}/server/main.py --gui
Icon={REPO_ROOT}/spen_icon.png
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
                f"Application menu entry created:\n{desktop_file}\n\nYou can now launch 'S Pen Bridge' from your app menu / launcher!",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install desktop launcher: {e}")
