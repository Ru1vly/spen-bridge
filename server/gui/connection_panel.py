"""
Quick Connect panel: LAN IP + port display, QR code pairing (APK download or
direct connect), and the USB/ADB low-latency forwarding shortcut.
"""

import logging
import subprocess

import qrcode
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
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

        qr_mode_row = QHBoxLayout()
        self.rb_qr_apk = QRadioButton("Download APK")
        self.rb_qr_apk.setChecked(True)
        self.rb_qr_apk.toggled.connect(self.update_qr_code)
        self.rb_qr_conn = QRadioButton("Direct Connect")
        self.rb_qr_conn.toggled.connect(self.update_qr_code)
        qr_mode_row.addWidget(self.rb_qr_apk)
        qr_mode_row.addWidget(self.rb_qr_conn)
        layout.addLayout(qr_mode_row)

        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        self.lbl_qr.setMinimumSize(115, 115)
        self.lbl_qr.setStyleSheet("background: #ffffff; border-radius: 8px; padding: 4px;")
        layout.addWidget(self.lbl_qr, alignment=Qt.AlignCenter)

        self.lbl_qr_hint = QLabel("Scan with tablet camera to download APK")
        self.lbl_qr_hint.setAlignment(Qt.AlignCenter)
        self.lbl_qr_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.lbl_qr_hint)

        self.btn_adb = QPushButton("Forward USB Port (ADB)")
        self.btn_adb.setToolTip("Sets up an ultra-low-latency USB cable connection via adb forward")
        self.btn_adb.clicked.connect(self.run_adb_forward)
        layout.addWidget(self.btn_adb)

        self.refresh_ip_label()
        self.update_qr_code()

    def refresh_ip_label(self):
        self.lbl_ip_info.setText(f"IP: <b>{self._local_ip}</b>   Port: <b>{self._config.port}</b>")

    def on_port_changed(self, port: int):
        self.refresh_ip_label()
        self.update_qr_code()

    def update_qr_code(self):
        if self.rb_qr_apk.isChecked():
            data = f"http://{self._local_ip}:8080/spen-on-linux.apk"
            self.lbl_qr_hint.setText(f"Scan to download APK (http://{self._local_ip}:8080)")
        else:
            data = f"spen://{self._local_ip}:{self._config.port}"
            self.lbl_qr_hint.setText(f"Server Target: {self._local_ip}:{self._config.port}")

        qr = qrcode.QRCode(box_size=3, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#11111b", back_color="#ffffff").convert("RGB")
        data_bytes = img.tobytes("raw", "RGB")
        qimg = QImage(data_bytes, img.size[0], img.size[1], QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(115, 115, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_qr.setPixmap(pix)

    def _copy_connection_info(self):
        text = f"{self._local_ip}:{self._config.port}"
        QApplication.clipboard().setText(text)
        self.lbl_ip_info.setText(f"IP: <b>{self._local_ip}</b>  (Copied!)")
        QTimer.singleShot(1500, self.refresh_ip_label)

    def run_adb_forward(self):
        self.log_message.emit(f"Running 'adb forward tcp:{self._config.port} tcp:{self._config.port}'...")
        try:
            res = subprocess.run(
                ["adb", "forward", f"tcp:{self._config.port}", f"tcp:{self._config.port}"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                self.log_message.emit("ADB forward successful! USB Mode ready.")
                self.btn_adb.setText("USB Active (ADB)")
                self.btn_adb.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
            else:
                err = res.stderr.strip() or "No device found"
                self.log_message.emit(f"ADB forward failed: {err}")
                QMessageBox.warning(
                    self,
                    "ADB Forward",
                    f"ADB forward returned error:\n{err}\n\nMake sure your tablet is connected via USB and USB Debugging is enabled.",
                )
        except FileNotFoundError:
            self.log_message.emit("ADB command not found.")
            QMessageBox.warning(
                self,
                "ADB Missing",
                "adb is not installed on this system.\nInstall with: sudo pacman -S android-tools (or sudo apt install adb)",
            )
        except Exception as e:
            self.log_message.emit(f"ADB forward error: {e}")
