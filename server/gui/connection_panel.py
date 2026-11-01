"""Pairing and connection details using the running listener's endpoint."""
import subprocess
import threading
import ipaddress

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QApplication, QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
)
from server.settings import listener_address
from server.security import load_identity


class ConnectionPanel(QGroupBox):
    log_message = Signal(str)
    adb_finished = Signal(bool, str, bool)
    connection_type_changed = Signal()

    def __init__(self, local_ip, config, parent=None):
        super().__init__("Connect your tablet", parent)
        self._local_ip, self._config = local_ip, config
        self._endpoint = None
        self._adb_thread = None
        self._adb_busy = False
        self._transitioning = False
        self._adb_deferred = None
        self._usb_ready = False
        self._peer = None
        self._last_adb_message = None
        self._usb_timer = QTimer(self)
        self._usb_timer.setInterval(2000)
        self._usb_timer.timeout.connect(lambda: self.run_adb_reverse(silent=True, automatic=True))
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.lbl_ip_info = QLabel()
        self.lbl_ip_info.setTextFormat(Qt.PlainText)
        self.lbl_ip_info.setWordWrap(True)
        row.addWidget(self.lbl_ip_info, 1)
        self.btn_copy = QPushButton("Copy address")
        self.btn_copy.clicked.connect(self._copy_connection_info)
        row.addWidget(self.btn_copy)
        layout.addLayout(row)
        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)
        self.lbl_transport = QLabel("No tablet connected")
        self.lbl_transport.setTextFormat(Qt.PlainText)
        self.lbl_transport.setWordWrap(True)
        layout.addWidget(self.lbl_transport)
        self.btn_pair = QPushButton("Pair tablet")
        self.btn_pair.setObjectName("primaryBtn")
        self.btn_pair.clicked.connect(self.show_pairing)
        layout.addWidget(self.btn_pair)
        self.btn_adb = QPushButton("Set up USB connection")
        self.btn_adb.clicked.connect(lambda: self.run_adb_reverse())
        layout.addWidget(self.btn_adb)
        self.adb_finished.connect(self._adb_done)
        self.refresh_ip_label()

    def set_transitioning(self):
        self._transitioning = True
        self.refresh_ip_label()

    def set_listener(self, endpoint):
        deferred, self._adb_deferred = self._adb_deferred, None
        self._endpoint = endpoint
        self._transitioning = False
        self.refresh_ip_label()
        if endpoint is None:
            self.set_client(None)
        if endpoint is not None and deferred is not None:
            self.run_adb_reverse(silent=deferred)

    def endpoint(self):
        return self._endpoint or (listener_address(self._config), self._config.port)

    def address(self):
        host, port = self.endpoint()
        host = self._local_ip if host in ("0.0.0.0", "::") else host
        return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"

    def refresh_ip_label(self):
        state = "Listener change in progress" if self._transitioning else (
            "Listening" if self._endpoint else "Not running")
        self.lbl_ip_info.setText(f"{state}: {self.address()}")
        self.btn_copy.setEnabled(not self._transitioning)
        self.btn_adb.setEnabled(not self._transitioning and not self._adb_busy)
        pending = self._endpoint and self._endpoint != (listener_address(self._config), self._config.port)
        self.lbl_hint.setText(
            "Network changes pending. Stop and start the server to apply them."
            if pending else "Connect your tablet by USB, or enable Wi-Fi in Preferences. Pair it to allow pen input."
        )

    def on_port_changed(self, port):
        self.refresh_ip_label()

    def _copy_connection_info(self):
        if not self._transitioning:
            QApplication.clipboard().setText(self.address())

    def show_pairing(self):
        try:
            identity = load_identity()
        except Exception as error:
            QMessageBox.warning(self, "Pairing unavailable", str(error))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Pair tablet")
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        hint = QLabel("Copy these into tablet Settings on your own device. The pairing code grants control of this desktop.")
        hint.setWordWrap(True)
        form.addRow(hint)
        for label, value in (("Certificate fingerprint", identity.fingerprint), ("Pairing code", identity.pairing_code)):
            row = QHBoxLayout()
            field = QLineEdit(value)
            field.setReadOnly(True)
            field.setAccessibleName(label)
            button = QPushButton("Copy")
            button.setAccessibleName(f"Copy {label.lower()}")
            button.clicked.connect(lambda checked=False, value=value: QApplication.clipboard().setText(value))
            row.addWidget(field, 1)
            row.addWidget(button)
            form.addRow(label, row)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        form.addRow(close)
        dialog.resize(600, dialog.sizeHint().height())
        dialog.exec()

    def connection_type(self):
        if not self._peer:
            return None
        host = self._peer.rsplit(":", 1)[0].strip("[]")
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        return ("USB (ADB)" if self._usb_ready else "Local") if local else "Wi-Fi / network"

    def set_client(self, peer):
        self._peer = peer
        self._refresh_transport()

    def _refresh_transport(self):
        kind = self.connection_type()
        self.lbl_transport.setText(f"Connected via {kind}" if kind else (
            "USB ready — waiting for paired tablet" if self._usb_ready else
            "USB reconnect enabled — waiting for device" if self._usb_timer.isActive() else
            "No tablet connected"))
        self.connection_type_changed.emit()

    def stop_usb_monitor(self):
        self._usb_timer.stop()
        if self._adb_thread and self._adb_thread.is_alive():
            # At most two commands, each with a five-second deadline.
            self._adb_thread.join(11)
        self._adb_deferred = None

    def run_adb_reverse(self, silent=False, *, automatic=False):
        if not automatic:
            self._usb_timer.start()
        if self._transitioning:
            if not automatic:
                self._adb_deferred = silent if self._adb_deferred is None else self._adb_deferred and silent
            return
        if self._adb_busy:
            return
        port = self.endpoint()[1]
        self._adb_busy = True
        self.btn_adb.setEnabled(False)
        if not automatic:
            self.log_message.emit(f"Enabling automatic USB forwarding for port {port}...")
        def run():
            try:
                ready = False
                if automatic:
                    listed = subprocess.run(["adb", "-d", "reverse", "--list"], capture_output=True,
                                            text=True, timeout=5, check=False)
                    if listed.returncode != 0:
                        self.adb_finished.emit(False, "USB reconnect enabled — waiting for an authorized device.", True)
                        return
                    ready = any(line.split()[1:] == [f"tcp:{port}", f"tcp:{port}"]
                                for line in listed.stdout.splitlines())
                if ready:
                    ok = True
                else:
                    result = subprocess.run(["adb", "-d", "reverse", f"tcp:{port}", f"tcp:{port}"],
                                            capture_output=True, text=True, timeout=5, check=False)
                    ok = result.returncode == 0
                message = (f"USB forwarding ready on port {port}; reconnect is automatic." if ok else
                           "USB reconnect enabled — waiting for an authorized device. Check the cable and USB debugging.")
            except FileNotFoundError:
                ok, message = False, "ADB is not installed or is not on PATH. Install Android Platform Tools, then enable USB mode again."
            except (OSError, subprocess.TimeoutExpired) as error:
                ok, message = False, f"USB forwarding failed: {error}"
            self.adb_finished.emit(ok, message[:2000], silent)
        self._adb_thread = threading.Thread(target=run, name="SPenADB", daemon=True)
        self._adb_thread.start()

    def _adb_done(self, ok, message, silent):
        self._adb_busy = False
        self._usb_ready = ok
        self.btn_adb.setEnabled(not self._transitioning)
        self.btn_adb.setText("Set up USB connection")
        if message != self._last_adb_message:
            self.log_message.emit(message)
            self._last_adb_message = message
        self._refresh_transport()
        if not ok and not silent:
            QMessageBox.warning(self, "USB forwarding", message)
