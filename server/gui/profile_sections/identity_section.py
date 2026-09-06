"""
Profile Identity & Matching section: which window names/classes activate this
profile automatically, plus a live indicator of whether the currently focused
window matches any of them.
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QToolButton

from server.config import AppProfile
from server.gui.widgets.chip_input import MatchChipInput
from server.gui.widgets.pill_badge import PillBadge

GUIDE_TEXT = (
    "How Profiles Work:\n"
    "- Default defines your global baseline settings, used when no other profile matches.\n"
    "- Application Profiles override settings when a matching application is focused.\n"
    "- Enter window class / process name substrings above; when any matching application is\n"
    "  focused, this profile activates automatically (if Auto-Switch is enabled).\n"
    "- Every field in this panel (device mode, pressure, buttons, mapping) is fully independent\n"
    "  per profile — changing one profile never affects another."
)


class IdentitySection(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Profile Identity && Matching", parent)
        self._profile: Optional[AppProfile] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Applies when the focused window matches:"))
        header_row.addStretch()
        btn_help = QToolButton()
        btn_help.setText("?")
        btn_help.setFixedSize(18, 18)
        btn_help.setStyleSheet("border: 1px solid #45475a; border-radius: 9px;")
        btn_help.setToolTip(GUIDE_TEXT)
        header_row.addWidget(btn_help)
        layout.addLayout(header_row)

        self.chip_input = MatchChipInput()
        self.chip_input.chips_changed.connect(self._on_chips_changed)
        layout.addWidget(self.chip_input)

        self.lbl_default_note = QLabel(
            "Used when no other profile matches — Default has no match rules of its own."
        )
        self.lbl_default_note.setWordWrap(True)
        self.lbl_default_note.setStyleSheet("color: #a6adc8; font-style: italic;")
        layout.addWidget(self.lbl_default_note)

        live_row = QHBoxLayout()
        self.lbl_live_match = QLabel("Detected active window right now: —")
        self.lbl_live_match.setWordWrap(True)
        live_row.addWidget(self.lbl_live_match, stretch=1)
        self.badge_live_match = PillBadge("No match", state="idle")
        live_row.addWidget(self.badge_live_match)
        layout.addLayout(live_row)

    def set_profile(self, profile: AppProfile):
        self._updating = True
        try:
            self._profile = profile
            is_default = profile.name == "Default"
            self.chip_input.setVisible(not is_default)
            self.lbl_default_note.setVisible(is_default)
            self.chip_input.set_chips(profile.app_matches)
        finally:
            self._updating = False

    def _on_chips_changed(self, chips):
        if self._updating or self._profile is None:
            return
        self._profile.app_matches = list(chips)
        self.changed.emit()

    def update_live_match(self, app_id: str, title: str):
        """Called by MainWindow's focused-window poller. Mirrors
        TabletConfig.find_profile_for_app's substring rule exactly, so the
        indicator can never disagree with the real auto-switch logic."""
        self.chip_input.set_active_window(app_id, title)
        if self._profile is None:
            return
        app_id_l = (app_id or "").lower()
        title_l = (title or "").lower()
        matched = False
        for m in self._profile.app_matches:
            m = m.strip().lower()
            if m and (m in app_id_l or m in title_l):
                matched = True
                break
        display = app_id or title or "Desktop"
        if len(display) > 40:
            display = display[:38] + "…"
        self.lbl_live_match.setText(f'Detected active window right now: "{display}"')
        self.badge_live_match.set_state("ok" if matched else "idle", "Match" if matched else "No match")
