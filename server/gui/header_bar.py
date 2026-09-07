"""
Top header bar: app title, server status badge, active-profile selector,
server start/stop toggle, and save-config button.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QComboBox, QPushButton

from server.gui.widgets.pill_badge import PillBadge


class HeaderBar(QFrame):
    server_toggle_clicked = Signal()
    save_clicked = Signal()
    profile_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # NOTE: deliberately no local setStyleSheet() call here — setting a
        # stylesheet directly on a container widget stops the app-level
        # stylesheet from cascading into its children (a well-known Qt
        # gotcha), which would break every themed child below (the
        # successBtn/dangerBtn buttons, the PillBadge). Styled via the
        # objectName rule in theme.py instead.
        self.setObjectName("HeaderBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        title_label = QLabel("S Pen Bridge")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #89b4fa;")
        layout.addWidget(title_label)

        self.status_badge = PillBadge("● Server Stopped", state="bad")
        layout.addWidget(self.status_badge)

        layout.addStretch()

        self.lbl_active_mode_prefix = QLabel("Active:")
        self.lbl_active_mode_prefix.setStyleSheet("color: #a6adc8; font-weight: 600; font-size: 13px;")
        layout.addWidget(self.lbl_active_mode_prefix)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(160)
        self.combo_profiles.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo_profiles)

        layout.addSpacing(6)

        self.btn_server_toggle = QPushButton("Start Server")
        self.btn_server_toggle.setObjectName("successBtn")
        self.btn_server_toggle.clicked.connect(self.server_toggle_clicked.emit)
        layout.addWidget(self.btn_server_toggle)

        self.btn_save_config = QPushButton("Save Config")
        self.btn_save_config.clicked.connect(self.save_clicked.emit)
        layout.addWidget(self.btn_save_config)

    def populate_profiles(self, profile_names, active_name: str):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for name in profile_names:
            label = "Default (Global)" if name == "Default" else name
            self.combo_profiles.addItem(label, name)
        self.combo_profiles.blockSignals(False)
        self.set_active_profile(active_name)

    def set_active_profile(self, name: str):
        for i in range(self.combo_profiles.count()):
            if self.combo_profiles.itemData(i) == name:
                self.combo_profiles.blockSignals(True)
                self.combo_profiles.setCurrentIndex(i)
                self.combo_profiles.blockSignals(False)
                break

    def set_auto_switch_mode(self, auto: bool):
        self.lbl_active_mode_prefix.setText("Auto:" if auto else "Active:")
        self.combo_profiles.setEnabled(not auto)
        self.combo_profiles.setToolTip(
            "Auto-switch is enabled — the live profile follows the focused window. "
            "Uncheck 'Auto-switch by focused window' in the Profiles tab to pick manually."
            if auto
            else ""
        )

    def set_dirty(self, dirty: bool):
        self.btn_save_config.setText("Save Config *" if dirty else "Save Config")

    def set_server_status(self, status: str, message: str):
        text = f"● {message}"
        if status == "running":
            self.status_badge.set_state("warn", text)
            self.btn_server_toggle.setText("Stop Server")
            self.btn_server_toggle.setObjectName("dangerBtn")
        elif status == "stopped":
            self.status_badge.set_state("bad", text)
            self.btn_server_toggle.setText("Start Server")
            self.btn_server_toggle.setObjectName("successBtn")
        elif status == "connected":
            self.status_badge.set_state("ok", text)
        elif status == "error":
            self.status_badge.set_state("bad", "● Error")
            self.btn_server_toggle.setText("Retry Start")
            self.btn_server_toggle.setObjectName("primaryBtn")
        self._repolish_toggle_button()

    def _repolish_toggle_button(self):
        style = self.btn_server_toggle.style()
        style.unpolish(self.btn_server_toggle)
        style.polish(self.btn_server_toggle)

    def _on_combo_changed(self, index: int):
        name = self.combo_profiles.itemData(index)
        if name:
            self.profile_changed.emit(name)
