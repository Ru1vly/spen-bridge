"""
System & Startup Preferences panel: network port, startup toggles, device
identity, uinput permission check, desktop launcher installer, and the
global reset-to-defaults action.
"""

import os
import getpass
import shlex
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
    changed = Signal()
    device_name_changed = Signal()
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
        self.spin_port.setAccessibleName("Server port")
        self.spin_port.setRange(1, 65535)
        self.spin_port.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(self.spin_port)
        port_row.addStretch()
        layout.addLayout(port_row)

        self.chk_wifi = QCheckBox("Allow paired Wi-Fi connections")
        self.chk_wifi.setToolTip("Off: USB loopback only. On: paired tablets may connect over your network.")
        self.chk_wifi.toggled.connect(self._on_wifi_changed)
        layout.addWidget(self.chk_wifi)

        self.chk_autostart_server = QCheckBox("Auto-start server on app launch")
        self.chk_autostart_server.toggled.connect(lambda c: self._set_preference("auto_start_server", c))
        layout.addWidget(self.chk_autostart_server)

        self.chk_auto_adb = QCheckBox("Auto-forward USB ADB on launch")
        self.chk_auto_adb.toggled.connect(lambda c: self._set_preference("auto_adb_forward", c))
        layout.addWidget(self.chk_auto_adb)

        self.chk_tray = QCheckBox("Minimize to tray on window close")
        self.chk_tray.toggled.connect(lambda c: self._set_preference("minimize_to_tray", c))
        layout.addWidget(self.chk_tray)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Device Name:"))
        self.edit_dev_name = QLineEdit()
        self.edit_dev_name.setAccessibleName("Virtual device name")
        self.edit_dev_name.setMaxLength(256)
        self.edit_dev_name.textChanged.connect(lambda t: self._set_preference("device_name", t))
        self.edit_dev_name.editingFinished.connect(self.device_name_changed.emit)
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
            self.chk_wifi.setChecked(self._config.wifi_enabled)
            self.chk_autostart_server.setChecked(self._config.auto_start_server)
            self.chk_auto_adb.setChecked(self._config.auto_adb_forward)
            self.chk_tray.setChecked(self._config.minimize_to_tray)
            self.edit_dev_name.setText(self._config.device_name)
        finally:
            self._updating = False

    def _set_preference(self, name, value):
        if self._updating or getattr(self._config, name) == value:
            return
        setattr(self._config, name, value)
        self.changed.emit()

    def _on_wifi_changed(self, enabled):
        if self._updating:
            return
        self._config.wifi_enabled = enabled
        self._config.host = "0.0.0.0" if enabled else "127.0.0.1"
        self.changed.emit()

    def set_desktop_size(self, size):
        self.lbl_desktop_size.setText(f"Detected desktop: {size[0]}x{size[1]}")

    def _on_port_changed(self, value: int):
        if self._updating:
            return
        self._config.port = value
        self.port_changed.emit(value)
        self.changed.emit()

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
                self._run_elevated_script(setup_script)

    def _run_elevated_script(self, script_path: Path):
        import shutil
        if shutil.which("pkexec"):
            try:
                subprocess.Popen(["pkexec", "env", f"SPEN_BRIDGE_USER={getpass.getuser()}", "bash", str(script_path)])
                QMessageBox.information(
                    self,
                    "uinput Setup",
                    "Launched setup with pkexec. After authenticating, click 'Check / Setup uinput Permissions' again.",
                )
                return
            except Exception:
                pass

        # Try launching in a terminal emulator
        terminals = [
            ("x-terminal-emulator", ["-e"]),
            ("gnome-terminal", ["--"]),
            ("konsole", ["-e"]),
            ("xfce4-terminal", ["-e"]),
            ("kitty", ["--"]),
            ("alacritty", ["-e"]),
            ("xterm", ["-e"]),
        ]
        for term, args in terminals:
            if shutil.which(term):
                try:
                    cmd = [term] + args + ["bash", "-c", f"sudo env {shlex.quote('SPEN_BRIDGE_USER=' + getpass.getuser())} bash {shlex.quote(str(script_path))}; echo 'Press enter to exit.'; read -r line"]
                    subprocess.Popen(cmd)
                    return
                except Exception:
                    pass

        # Fallback: display command to user
        QMessageBox.information(
            self,
            "Run Setup Script",
            f"Please run the setup script in your terminal to grant permissions:\n\n"
            f"sudo env {shlex.quote('SPEN_BRIDGE_USER=' + getpass.getuser())} bash {shlex.quote(str(script_path))}\n\n"
            f"Then re-check permissions.",
        )

    def _install_desktop_entry(self):
        """Create and install .desktop file for system application launcher."""
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = apps_dir / "spen-bridge.desktop"

        try:
            from server.launcher import install_launcher
            install_launcher(REPO_ROOT, desktop_file)
            QMessageBox.information(
                self,
                "Desktop Launcher Installed",
                f"Application menu entry created:\n{desktop_file}\n\nYou can now launch 'S Pen Bridge' from your app menu / launcher!",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install desktop launcher: {e}")
