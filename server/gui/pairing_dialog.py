"""One-time nearby-tablet approval; credentials stay out of the interface."""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class PairingDialog(QDialog):
    decision = Signal(str, bool)
    retry = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pair tablet")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(360)
        self.resize(480, 320)
        self._token = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.heading = QLabel("Connect your tablet")
        self.heading.setObjectName("workspaceTitle")
        self.heading.setWordWrap(True)
        self.heading.setTextFormat(Qt.PlainText)
        layout.addWidget(self.heading)
        self.hint = QLabel("On your tablet, open Settings → Connection → Find desktop. Keep both devices on the same Wi-Fi network.")
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(Qt.PlainText)
        layout.addWidget(self.hint)
        self.number = QLabel()
        self.number.setAlignment(Qt.AlignCenter)
        self.number.setAccessibleName("Pairing verification number")
        self.number.setStyleSheet("font-size: 32px; font-weight: 600; padding: 12px;")
        self.number.hide()
        layout.addWidget(self.number)
        self.status = QLabel("Starting nearby pairing…")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        layout.addStretch()
        row = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        row.addWidget(self.cancel_button)
        self.allow_button = QPushButton("Allow device")
        self.allow_button.setObjectName("primaryBtn")
        self.allow_button.clicked.connect(self._allow)
        self.allow_button.hide()
        row.addWidget(self.allow_button)
        self.retry_button = QPushButton("Try again")
        self.retry_button.clicked.connect(self._retry)
        self.retry_button.hide()
        row.addWidget(self.retry_button)
        layout.addLayout(row)
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(lambda: self.finished_state(False, "Pairing expired. Try again when your tablet is ready."))

    def ready(self):
        self._token = None
        self.heading.setText("Connect your tablet")
        self.hint.setText("On your tablet, open Settings → Connection → Find desktop. Keep both devices on the same Wi-Fi network.")
        self.status.setText("Ready for a nearby tablet. Pairing is available for two minutes.")
        self.number.hide()
        self.allow_button.hide()
        self.retry_button.hide()
        self.cancel_button.setText("Cancel")
        self.expiry.start(120000)

    def show_request(self, request):
        self._token = request.token
        self.heading.setText(f"Allow {request.device_name} to connect?")
        self.hint.setText("Check that this number matches the number on your tablet, then allow the connection.")
        self.number.setText(request.number)
        self.number.show()
        self.status.setText("Only allow a tablet you are setting up.")
        self.allow_button.show()
        self.cancel_button.setText("Deny")
        self.expiry.start(max(1, int(request.expires_in * 1000)))

    def _allow(self):
        if self._token:
            self.decision.emit(self._token, True)
            self.allow_button.setEnabled(False)
            self.status.setText("Finishing pairing…")

    def _cancel(self):
        if self._token:
            self.decision.emit(self._token, False)
        self.reject()

    def _retry(self):
        self.allow_button.setEnabled(True)
        self.status.setText("Starting nearby pairing…")
        self.retry_button.hide()
        self.retry.emit()

    def finished_state(self, approved, message):
        self.expiry.stop()
        if not approved and self._token:
            self.decision.emit(self._token, False)
        self._token = None
        self.heading.setText("Tablet paired" if approved else "Pairing not completed")
        self.hint.setText("Your devices will reconnect automatically. You can return to drawing." if approved else message)
        self.status.setText(message)
        self.number.hide()
        self.allow_button.hide()
        self.retry_button.setVisible(not approved)
        self.cancel_button.setText("Close")
