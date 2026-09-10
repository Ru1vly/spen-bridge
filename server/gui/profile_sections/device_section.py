"""
Device Behavior profile section: pointer vs tablet device mode, click-on-touch,
and (advanced) INPUT_PROP_DIRECT mode: all per-profile.
"""

import sys
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox

from server.config import AppProfile
from server.gui.widgets.collapsible_box import CollapsibleBox


class DeviceSection(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Device Behavior", parent)
        self._profile: Optional[AppProfile] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Device Type:"))
        self.combo_dev_mode = QComboBox()
        self.combo_dev_mode.addItem("Pointer Mode (Absolute Cursor - Wayland & X11)", "pointer")
        self.combo_dev_mode.addItem("Tablet Mode (Wacom Tablet-v2 for Krita/GIMP)", "tablet")
        if sys.platform == "win32":
            self.combo_dev_mode.setItemText(0, "Windows Ink Pen")
            self.combo_dev_mode.setItemText(1, "Windows Ink Pen")
            self.combo_dev_mode.setEnabled(False)
        self.combo_dev_mode.currentIndexChanged.connect(self._on_dev_mode_changed)
        mode_row.addWidget(self.combo_dev_mode, stretch=1)
        layout.addLayout(mode_row)

        self.chk_click_on_touch = QCheckBox(
            "Enable Click on Touch (pen contact generates mouse clicks / touch events)"
        )
        self.chk_click_on_touch.toggled.connect(self._on_click_on_touch_toggled)
        layout.addWidget(self.chk_click_on_touch)

        desc = QLabel(
            "When disabled, hovering, movement, and pressure are tracked without emitting mouse "
            "click events, ideal for keyboard-tapping rhythm games, custom gesture controls, or "
            "hover-only navigation."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(desc)

        self.advanced_box = CollapsibleBox("Advanced: Direct Input Mode")
        self.chk_direct_mode = QCheckBox("Enable INPUT_PROP_DIRECT (Display Tablet Mode)")
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
