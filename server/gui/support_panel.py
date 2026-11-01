"""User-opened support. Diagnostic export is an allowlist, never a log dump."""
import platform
from importlib.metadata import PackageNotFoundError, version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from server.gui.widgets.collapsible_box import CollapsibleBox


class SupportPanel(CollapsibleBox):
    def __init__(self, config, parent=None):
        super().__init__("Help and support", parent)
        layout = self.body_layout()
        help_text = QLabel(
            "USB: connect a data cable, enable USB debugging on the tablet, then choose "
            "Set up USB connection on the Connection page. Accept the tablet's debugging prompt.\n\n"
            "Wi-Fi: connect both devices to the same network. Enable paired Wi-Fi connections "
            "in Preferences, restart the server, then pair from the Connection page.\n\n"
            "No pen input: check the connection, then try your pen in a desktop application. "
            "On Linux, check input permissions in Preferences. Windows pen input is experimental.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.report = QLabel()
        self.report.setWordWrap(True)
        self.report.setTextFormat(Qt.PlainText)
        layout.addWidget(self.report)
        self.copy_button = QPushButton("Copy diagnostic report")
        layout.addWidget(self.copy_button)
        self._config = config
        self.copy_button.clicked.connect(lambda: self.copy_report(self._config))
        self.refresh_report(config)

    def refresh_report(self, config):
        self._config = config
        try:
            app_version = version("spen-bridge")
        except PackageNotFoundError:
            app_version = "source checkout"
        self.report_text = (f"S Pen Bridge\nVersion: {app_version}\nSystem: {platform.system()}\n"
                            f"Wi-Fi enabled: {config.wifi_enabled}\n"
                            f"Automatic USB setup: {config.auto_adb_forward}\n"
                            "Pairing credentials, addresses, application names and logs are excluded.")
        self.report.setText(self.report_text)

    def copy_report(self, config):
        self.refresh_report(config)
        QApplication.clipboard().setText(self.report_text)
        self.copy_button.setText("Report copied")
