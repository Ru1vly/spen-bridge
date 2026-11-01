"""
Device behavior profile section: pointer vs tablet device mode, click-on-touch,
and (advanced) INPUT_PROP_DIRECT mode: all per-profile.
"""

from server.gui.theme import PALETTE


import sys
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox

from server.config import AppProfile
from server.gui.widgets.collapsible_box import CollapsibleBox


class DeviceSection(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Device behavior", parent)
        self._profile: Optional[AppProfile] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Device type:"))
        self.combo_dev_mode = QComboBox()
        self.combo_dev_mode.setAccessibleName("Device type")
        self.combo_dev_mode.addItem("Pointer (absolute cursor)", "pointer")
        self.combo_dev_mode.addItem("Tablet (Wacom tablet protocol)", "tablet")
        if sys.platform == "win32":
            self.combo_dev_mode.setItemText(0, "Windows Ink pen")
            self.combo_dev_mode.setItemText(1, "Windows Ink pen")
            self.combo_dev_mode.setEnabled(False)
        self.combo_dev_mode.currentIndexChanged.connect(self._on_dev_mode_changed)
        mode_row.addWidget(self.combo_dev_mode, stretch=1)
        layout.addLayout(mode_row)

        self.chk_click_on_touch = QCheckBox(
            "Generate clicks on pen contact"
        )
        self.chk_click_on_touch.toggled.connect(self._on_click_on_touch_toggled)
        layout.addWidget(self.chk_click_on_touch)

        desc = QLabel(
            "Turn off to move the pointer without clicking when the pen touches the tablet. "
            "Pressure and hover events are still sent."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        layout.addWidget(desc)

        self.advanced_box = CollapsibleBox("Advanced: direct input")
        self.chk_direct_mode = QCheckBox("Direct input (display tablet)")
        self.chk_direct_mode.toggled.connect(self._on_direct_mode_toggled)
        self.advanced_box.body_layout().addWidget(self.chk_direct_mode)
        layout.addWidget(self.advanced_box)
        if sys.platform == "win32":
            self.advanced_box.hide()

    def set_profile(self, profile: AppProfile):
        self._updating = True
        try:
            self._profile = profile
            idx = 1 if profile.device_mode == "tablet" else 0
            self.combo_dev_mode.setCurrentIndex(idx)
            self.chk_click_on_touch.setChecked(profile.click_on_touch)
            self.chk_direct_mode.setChecked(profile.direct_mode)
            self.advanced_box.set_expanded(profile.direct_mode)
            self.advanced_box.set_summary(f"direct mode: {'on' if profile.direct_mode else 'off'}")
        finally:
            self._updating = False

    def _on_dev_mode_changed(self, index: int):
        if self._updating or self._profile is None:
            return
        self._profile.device_mode = self.combo_dev_mode.currentData()
        self.changed.emit()

    def _on_click_on_touch_toggled(self, checked: bool):
        if self._updating or self._profile is None:
            return
        self._profile.click_on_touch = checked
        self.changed.emit()

    def _on_direct_mode_toggled(self, checked: bool):
        self.advanced_box.set_summary(f"direct mode: {'on' if checked else 'off'}")
        if self._updating or self._profile is None:
            return
        self._profile.direct_mode = checked
        self.changed.emit()
