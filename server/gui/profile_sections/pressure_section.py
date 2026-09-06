"""
Pressure Sensitivity Curve & Deadzone profile section: presets, gamma/min/max
sliders, the live pressure-curve graph, and raw/calibrated pressure meters.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QSlider,
    QPushButton,
    QButtonGroup,
    QProgressBar,
)

from server.config import AppProfile
from server.widgets.pressure_curve import PressureCurveWidget

PRESETS = [
    ("Linear", "linear", 1.0),
    ("Soft", "soft", 0.65),
    ("Firm", "firm", 1.6),
    ("Sigmoid", "sigmoid", 1.0),
]


class PressureSection(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Pressure Sensitivity Curve && Deadzone", parent)
        self._profile: Optional[AppProfile] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))
        self.preset_btn_group = QButtonGroup(self)
        self.preset_btn_group.setExclusive(True)
        for idx, (title, c_type, g_val) in enumerate(PRESETS):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, ct=c_type, g=g_val: self._apply_preset(ct, g))
            self.preset_btn_group.addButton(btn, idx)
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

        grid = QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(QLabel("Sensitivity Exponent (Gamma):"), 0, 0)
        self.lbl_gamma_val = QLabel("1.00")
        self.lbl_gamma_val.setStyleSheet("font-weight: bold; color: #89b4fa;")
        grid.addWidget(self.lbl_gamma_val, 0, 1)
        self.slider_gamma = QSlider(Qt.Horizontal)
        self.slider_gamma.setRange(20, 300)
        self.slider_gamma.valueChanged.connect(self._on_gamma_changed)
        grid.addWidget(self.slider_gamma, 1, 0, 1, 2)

        grid.addWidget(QLabel("Minimum Pressure Threshold (Deadzone):"), 2, 0)
        self.lbl_min_val = QLabel("0%")
        self.lbl_min_val.setStyleSheet("font-weight: bold; color: #f38ba8;")
        grid.addWidget(self.lbl_min_val, 2, 1)
        self.slider_min = QSlider(Qt.Horizontal)
        self.slider_min.setRange(0, 30)
        self.slider_min.valueChanged.connect(self._on_min_changed)
        grid.addWidget(self.slider_min, 3, 0, 1, 2)

        grid.addWidget(QLabel("Maximum Pressure Ceiling (100% Force):"), 4, 0)
        self.lbl_max_val = QLabel("100%")
        self.lbl_max_val.setStyleSheet("font-weight: bold; color: #fab387;")
        grid.addWidget(self.lbl_max_val, 4, 1)
        self.slider_max = QSlider(Qt.Horizontal)
        self.slider_max.setRange(70, 100)
        self.slider_max.valueChanged.connect(self._on_max_changed)
        grid.addWidget(self.slider_max, 5, 0, 1, 2)

        layout.addLayout(grid)

        self.curve_widget = PressureCurveWidget()
        layout.addWidget(self.curve_widget, stretch=1)

        meter_grid = QGridLayout()
        meter_grid.setSpacing(4)
        meter_grid.addWidget(QLabel("Raw Input:"), 0, 0)
        self.bar_raw = QProgressBar()
        self.bar_raw.setRange(0, 100)
        meter_grid.addWidget(self.bar_raw, 0, 1)
        meter_grid.addWidget(QLabel("Calibrated:"), 1, 0)
        self.bar_cal = QProgressBar()
        self.bar_cal.setRange(0, 100)
        meter_grid.addWidget(self.bar_cal, 1, 1)
        layout.addLayout(meter_grid)

    def set_profile(self, profile: AppProfile):
        self._updating = True
        try:
            self._profile = profile
            preset_matched = False
            for btn in self.preset_btn_group.buttons():
                first_word = btn.text().split()[0].lower()
                if first_word == profile.pressure_curve_type:
                    btn.setChecked(True)
                    preset_matched = True
                    break
            if not preset_matched:
                checked_btn = self.preset_btn_group.checkedButton()
                if checked_btn:
                    self.preset_btn_group.setExclusive(False)
                    checked_btn.setChecked(False)
                    self.preset_btn_group.setExclusive(True)

            self.slider_gamma.setValue(int(profile.pressure_gamma * 100))
            self.lbl_gamma_val.setText(f"{profile.pressure_gamma:.2f}")
            self.slider_min.setValue(int(profile.pressure_min * 100))
            self.lbl_min_val.setText(f"{int(profile.pressure_min * 100)}%")
            self.slider_max.setValue(int(profile.pressure_max * 100))
            self.lbl_max_val.setText(f"{int(profile.pressure_max * 100)}%")
            self._sync_curve_widget()
        finally:
            self._updating = False

    def _sync_curve_widget(self):
        if self._profile is None:
            return
        self.curve_widget.set_params(
            curve_type=self._profile.pressure_curve_type,
            gamma=self._profile.pressure_gamma,
            p_min=self._profile.pressure_min,
            p_max=self._profile.pressure_max,
        )

    def _apply_preset(self, curve_type: str, gamma: float):
        if self._updating or self._profile is None:
            return
        self._profile.pressure_curve_type = curve_type
        self._profile.pressure_gamma = gamma
        self._updating = True
        try:
            self.slider_gamma.setValue(int(gamma * 100))
            self.lbl_gamma_val.setText(f"{gamma:.2f}")
        finally:
            self._updating = False
        self._sync_curve_widget()
        self.changed.emit()

    def _on_gamma_changed(self, val: int):
        if self._updating or self._profile is None:
            return
        gamma = val / 100.0
        self._profile.pressure_gamma = gamma
        self._profile.pressure_curve_type = "custom"
        self.lbl_gamma_val.setText(f"{gamma:.2f}")
        self._sync_curve_widget()
        self.changed.emit()

    def _on_min_changed(self, val: int):
        if self._updating or self._profile is None:
            return
        p_min = val / 100.0
        self._profile.pressure_min = p_min
        self.lbl_min_val.setText(f"{val}%")
        self._sync_curve_widget()
        self.changed.emit()

    def _on_max_changed(self, val: int):
        if self._updating or self._profile is None:
            return
        p_max = val / 100.0
        self._profile.pressure_max = p_max
        self.lbl_max_val.setText(f"{val}%")
        self._sync_curve_widget()
        self.changed.emit()
