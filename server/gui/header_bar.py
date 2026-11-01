"""
Top header bar: app title, server status badge, active-profile selector,
server start/stop toggle, and save-config button.
"""

from server.gui.theme import PALETTE


from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton

from server.gui.widgets.pill_badge import PillBadge


class HeaderBar(QFrame):
    server_toggle_clicked = Signal()
    save_clicked = Signal()
    profile_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # NOTE: deliberately no local setStyleSheet() call here: setting a
        # stylesheet directly on a container widget stops the app-level
        # stylesheet from cascading into its children (a well-known Qt
        # gotcha), which would break every themed child below (the
        # successBtn/dangerBtn buttons, the PillBadge). Styled via the
        # objectName rule in theme.py instead.
        self.setObjectName("HeaderBar")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 12)
        outer.setSpacing(16)
        identity = QVBoxLayout()
        title_label = QLabel("S Pen Bridge")
        title_label.setObjectName("pageTitle")
        identity.addWidget(title_label)
        self.status_badge = PillBadge("Server stopped", state="idle")
        self.status_badge.setWordWrap(True)
        identity.addWidget(self.status_badge, 0, Qt.AlignLeft)
        self.profile_summary = QLabel("Using: Default")
        self.profile_summary.setObjectName("supportingText")
        self.profile_summary.setTextFormat(Qt.PlainText)
        self.profile_summary.setWordWrap(True)
        identity.addWidget(self.profile_summary)
        outer.addLayout(identity, 1)
        self.btn_server_toggle = QPushButton("Start server")
        self.btn_server_toggle.setObjectName("successBtn")
        self.btn_server_toggle.clicked.connect(self.server_toggle_clicked.emit)
        outer.addWidget(self.btn_server_toggle, 0, Qt.AlignTop)
        self.btn_save_config = QPushButton("Save settings")
        self.btn_save_config.setToolTip("Save changes for the next launch. Pen settings apply immediately; network changes require a server restart.")
        self.btn_save_config.clicked.connect(self.save_clicked.emit)
        saving = QVBoxLayout()
        saving.addWidget(self.btn_save_config)
        self.save_feedback = QLabel("Settings saved")
        self.save_feedback.setObjectName("supportingText")
        self.save_feedback.setWordWrap(True)
        self.save_feedback.setAccessibleName("Settings save status")
        saving.addWidget(self.save_feedback)
        outer.addLayout(saving)
        self.btn_save_config.setEnabled(False)

        self.profile_context = QFrame()
        context = QVBoxLayout(self.profile_context)
        context.setContentsMargins(0, 0, 0, 0)
        self.lbl_active_mode_prefix = QLabel("Active profile")
        self.lbl_active_mode_prefix.setObjectName("supportingText")
        context.addWidget(self.lbl_active_mode_prefix)
        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(0)
        self.combo_profiles.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_profiles.setMinimumContentsLength(8)
        self.combo_profiles.setAccessibleName("Active profile")
        self.combo_profiles.currentIndexChanged.connect(self._on_combo_changed)
        context.addWidget(self.combo_profiles)

    def populate_profiles(self, profile_names, active_name: str):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for name in profile_names:
            label = "Default (Global)" if name == "Default" else name
            self.combo_profiles.addItem(label, name)
        self.combo_profiles.blockSignals(False)
        self.set_active_profile(active_name)

    def set_active_profile(self, name: str):
        self.profile_summary.setText(f"Using: {name}")
        for i in range(self.combo_profiles.count()):
            if self.combo_profiles.itemData(i) == name:
                self.combo_profiles.blockSignals(True)
                self.combo_profiles.setCurrentIndex(i)
                self.combo_profiles.blockSignals(False)
                break

    def set_auto_switch_mode(self, auto: bool):
        self.lbl_active_mode_prefix.setText("Automatic profile" if auto else "Active profile")
        self.combo_profiles.setEnabled(not auto)
        self.combo_profiles.setToolTip(
            "Automatic switching is on. Turn it off in App profiles to choose a profile here."
            if auto
            else ""
        )

    def set_dirty(self, dirty: bool):
        self.btn_save_config.setText("Save settings")
        self.btn_save_config.setEnabled(dirty)
        self.save_feedback.setText("Unsaved changes" if dirty else "Settings saved")

    def set_server_status(self, status: str, message: str):
        text = message
        self.status_badge.setToolTip(message)
        if status == "running":
            self.status_badge.set_state("warn", text)
            self.btn_server_toggle.setText("Stop server")
            self.btn_server_toggle.setObjectName("dangerBtn")
        elif status == "stopped":
            self.status_badge.set_state("idle", text)
            self.btn_server_toggle.setText("Start server")
            self.btn_server_toggle.setObjectName("successBtn")
        elif status == "connected":
            self.status_badge.set_state("ok", text)
        elif status == "error":
            self.status_badge.set_state("bad", "● Error")
            self.btn_server_toggle.setText("Try again")
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
