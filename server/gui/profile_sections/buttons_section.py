"""
Hardware Buttons & Stroke Smoothing profile section: barrel button actions
and stroke jitter-reduction smoothing.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QGridLayout, QLabel, QComboBox, QSlider

from server.config import AppProfile


class ButtonsSection(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Hardware Buttons && Stroke Smoothing", parent)
        self._profile: Optional[AppProfile] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("Primary Button (Side Barrel):"), 0, 0)
        self.combo_btn_prim = QComboBox()
        self.combo_btn_prim.addItem("Right Click (Default — Context Menu / Color Picker)", "right_click")
        self.combo_btn_prim.addItem("Middle Click (Pan / Rotate Canvas)", "middle_click")
        self.combo_btn_prim.addItem("Toggle Eraser Mode", "eraser")
        self.combo_btn_prim.addItem("Undo Shortcut (Ctrl+Z)", "undo")
        self.combo_btn_prim.addItem("Wacom Stylus Button (e.BTN_STYLUS)", "stylus")
        self.combo_btn_prim.addItem("Disabled", "none")
        self.combo_btn_prim.currentIndexChanged.connect(self._on_primary_changed)
        grid.addWidget(self.combo_btn_prim, 0, 1)

        grid.addWidget(QLabel("Secondary Button:"), 1, 0)
        self.combo_btn_sec = QComboBox()
        self.combo_btn_sec.addItem("Middle Click (Default)", "middle_click")
        self.combo_btn_sec.addItem("Right Click", "right_click")
        self.combo_btn_sec.addItem("Toggle Eraser Mode", "eraser")
        self.combo_btn_sec.addItem("Undo Shortcut (Ctrl+Z)", "undo")
        self.combo_btn_sec.addItem("Wacom Stylus 2 (e.BTN_STYLUS2)", "stylus2")
        self.combo_btn_sec.addItem("Disabled", "none")
        self.combo_btn_sec.currentIndexChanged.connect(self._on_secondary_changed)
        grid.addWidget(self.combo_btn_sec, 1, 1)

        layout.addLayout(grid)

        sm_header = QGridLayout()
        sm_header.addWidget(QLabel("Smoothing Filter Strength:"), 0, 0)
        self.lbl_smooth_val = QLabel("0%")
        self.lbl_smooth_val.setStyleSheet("font-weight: bold; color: #a6e3a1;")
        sm_header.addWidget(self.lbl_smooth_val, 0, 1)
        layout.addLayout(sm_header)

        self.slider_smooth = QSlider(Qt.Horizontal)
        self.slider_smooth.setRange(0, 85)
        self.slider_smooth.valueChanged.connect(self._on_smooth_changed)
        layout.addWidget(self.slider_smooth)

        desc = QLabel("Filters coordinate noise and stabilizes lines for drawing or handwriting.")
        desc.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(desc)

    def set_profile(self, profile: AppProfile):
        self._updating = True
        try:
            self._profile = profile
            for i in range(self.combo_btn_prim.count()):
                if self.combo_btn_prim.itemData(i) == profile.button_primary:
                    self.combo_btn_prim.setCurrentIndex(i)
                    break
            for i in range(self.combo_btn_sec.count()):
                if self.combo_btn_sec.itemData(i) == profile.button_secondary:
                    self.combo_btn_sec.setCurrentIndex(i)
                    break
            self.slider_smooth.setValue(int(profile.stroke_smoothing * 100))
            self.lbl_smooth_val.setText(f"{int(profile.stroke_smoothing * 100)}%")
        finally:
            self._updating = False

    def _on_primary_changed(self, index: int):
        if self._updating or self._profile is None:
            return
        self._profile.button_primary = self.combo_btn_prim.currentData()
        self.changed.emit()

    def _on_secondary_changed(self, index: int):
        if self._updating or self._profile is None:
            return
        self._profile.button_secondary = self.combo_btn_sec.currentData()
        self.changed.emit()

    def _on_smooth_changed(self, val: int):
        if self._updating or self._profile is None:
            return
        self._profile.stroke_smoothing = val / 100.0
        self.lbl_smooth_val.setText(f"{val}%")
        self.changed.emit()
