"""
Screen Mapping profile section: which screen region the tablet surface maps
to (whole desktop / single monitor / custom rect), plus the always-visible,
globally-scoped aspect ratio lock (applies to all profiles — see the GUI
redesign spec section 4 for why aspect ratio stays global for this pass).
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QRadioButton,
    QComboBox,
    QPushButton,
    QSpinBox,
    QCheckBox,
)

from server.config import AppProfile, TabletConfig
from server.gui.widgets.collapsible_box import CollapsibleBox
from server.monitors import detect_monitors
from server.widgets.monitor_layout import MonitorLayoutWidget

DEFAULT_CUSTOM_BOUNDS = [0, 0, 1920, 1080]


class MappingSection(QGroupBox):
    changed = Signal()
    monitors_refreshed = Signal(tuple)

    def __init__(self, config: TabletConfig, parent=None):
        super().__init__("Screen Mapping", parent)
        self._config = config
        self._profile: Optional[AppProfile] = None
        self._updating = False
        self._updating_global = False
        self.monitors, self.desktop_size = detect_monitors()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.rb_map_all = QRadioButton("Whole Virtual Desktop (spanning all screens)")
        self.rb_map_all.toggled.connect(self._on_mapping_mode_changed)
        layout.addWidget(self.rb_map_all)

        self.rb_map_mon = QRadioButton("Single Monitor:")
        self.rb_map_mon.toggled.connect(self._on_mapping_mode_changed)
        layout.addWidget(self.rb_map_mon)

        mon_row = QHBoxLayout()
        self.combo_monitors = QComboBox()
        self.combo_monitors.currentIndexChanged.connect(self._on_monitor_combo_changed)
        mon_row.addWidget(self.combo_monitors, stretch=1)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_monitors)
        mon_row.addWidget(btn_refresh)
        layout.addLayout(mon_row)

        self.monitor_widget = MonitorLayoutWidget()
        self.monitor_widget.monitor_clicked.connect(self._on_monitor_clicked_on_map)
        layout.addWidget(self.monitor_widget, stretch=1)

        self.rb_map_custom = QRadioButton("Custom Rectangle:")
        self.rb_map_custom.toggled.connect(self._on_mapping_mode_changed)
        layout.addWidget(self.rb_map_custom)

        self.advanced_box = CollapsibleBox("Advanced: Exact Pixel Bounds")
        custom_grid = QGridLayout()
        custom_grid.addWidget(QLabel("X:"), 0, 0)
        self.spin_cust_x = QSpinBox()
        self.spin_cust_x.setRange(0, 10000)
        self.spin_cust_x.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_x, 0, 1)

        custom_grid.addWidget(QLabel("Y:"), 0, 2)
        self.spin_cust_y = QSpinBox()
        self.spin_cust_y.setRange(0, 10000)
        self.spin_cust_y.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_y, 0, 3)

        custom_grid.addWidget(QLabel("Width:"), 1, 0)
        self.spin_cust_w = QSpinBox()
        self.spin_cust_w.setRange(100, 10000)
        self.spin_cust_w.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_w, 1, 1)

        custom_grid.addWidget(QLabel("Height:"), 1, 2)
        self.spin_cust_h = QSpinBox()
        self.spin_cust_h.setRange(100, 10000)
        self.spin_cust_h.valueChanged.connect(self._on_custom_bounds_changed)
        custom_grid.addWidget(self.spin_cust_h, 1, 3)
        self.advanced_box.body_layout().addLayout(custom_grid)
        layout.addWidget(self.advanced_box)

        self.lbl_map_info = QLabel()
        self.lbl_map_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.lbl_map_info)

        ar_row = QHBoxLayout()
        self.chk_aspect_lock = QCheckBox("Lock Aspect Ratio")
        self.chk_aspect_lock.toggled.connect(self._on_aspect_lock_changed)
        ar_row.addWidget(self.chk_aspect_lock)
        self.combo_aspect_ratio = QComboBox()
        self.combo_aspect_ratio.addItems(["16:10", "16:9", "4:3", "21:9", "3:2"])
        self.combo_aspect_ratio.currentTextChanged.connect(self._on_aspect_ratio_changed)
        ar_row.addWidget(self.combo_aspect_ratio)
        lbl_global_note = QLabel("(applies to all profiles)")
        lbl_global_note.setStyleSheet("color: #6c7086; font-size: 11px;")
        ar_row.addWidget(lbl_global_note)
        ar_row.addStretch()
        layout.addLayout(ar_row)

        self._populate_monitor_combo()
        self._sync_global_controls()

    def set_profile(self, profile: AppProfile):
        self._updating = True
        try:
            self._profile = profile
            if profile.mapping_mode == "all":
                self.rb_map_all.setChecked(True)
            elif profile.mapping_mode == "monitor":
                self.rb_map_mon.setChecked(True)
            elif profile.mapping_mode == "custom":
                self.rb_map_custom.setChecked(True)

            for i in range(self.combo_monitors.count()):
                if self.combo_monitors.itemData(i) == profile.selected_monitor:
                    self.combo_monitors.setCurrentIndex(i)
                    break

            bounds = profile.custom_bounds
            if len(bounds) == 4:
                self.spin_cust_x.setValue(bounds[0])
                self.spin_cust_y.setValue(bounds[1])
                self.spin_cust_w.setValue(bounds[2])
                self.spin_cust_h.setValue(bounds[3])
                self.advanced_box.set_summary(f"custom bounds: {bounds[0]},{bounds[1]} {bounds[2]}x{bounds[3]}")
            else:
                self.advanced_box.set_summary("not set")

            self.advanced_box.set_expanded(
                profile.mapping_mode == "custom" or list(bounds) != DEFAULT_CUSTOM_BOUNDS
            )
            self._update_monitor_widget()
        finally:
            self._updating = False

    def _sync_global_controls(self):
        self._updating_global = True
        try:
            self.chk_aspect_lock.setChecked(self._config.aspect_ratio_lock)
            self.combo_aspect_ratio.setCurrentText(self._config.tablet_aspect_ratio)
        finally:
            self._updating_global = False

    def _populate_monitor_combo(self):
        self.combo_monitors.blockSignals(True)
        self.combo_monitors.clear()
        for mon in self.monitors:
            label = f"{mon['name']} ({mon['width']}x{mon['height']} at +{mon['x']}+{mon['y']})"
            self.combo_monitors.addItem(label, mon["name"])
        self.combo_monitors.blockSignals(False)

    def _refresh_monitors(self):
        self.monitors, self.desktop_size = detect_monitors()
        self._config.desktop_size = [self.desktop_size[0], self.desktop_size[1]]
        self._populate_monitor_combo()
        if self._profile is not None:
            self._updating = True
            try:
                for i in range(self.combo_monitors.count()):
                    if self.combo_monitors.itemData(i) == self._profile.selected_monitor:
                        self.combo_monitors.setCurrentIndex(i)
                        break
            finally:
                self._updating = False
        self._update_monitor_widget()
        self.monitors_refreshed.emit(tuple(self.desktop_size))
        self.changed.emit()

    def _update_monitor_widget(self):
        if self._profile is None:
            return
        self.monitor_widget.set_data(
            monitors=self.monitors,
            desktop_size=self.desktop_size,
            mapping_mode=self._profile.mapping_mode,
            selected_monitor=self._profile.selected_monitor,
            custom_bounds=tuple(self._profile.custom_bounds),
        )
        total_w, total_h = self.desktop_size
        if self._profile.mapping_mode == "all":
            desc = f"Active Area: Entire Virtual Desktop ({total_w}x{total_h})"
        elif self._profile.mapping_mode == "monitor":
            desc = f"Active Area: Single Monitor ({self._profile.selected_monitor})"
        else:
            cb = self._profile.custom_bounds
            desc = f"Active Area: Custom Rect ({cb[0]},{cb[1]} {cb[2]}x{cb[3]})"
        self.lbl_map_info.setText(desc)

    def _on_mapping_mode_changed(self):
        if self._updating or self._profile is None:
            return
        if self.rb_map_all.isChecked():
            self._profile.mapping_mode = "all"
        elif self.rb_map_mon.isChecked():
            self._profile.mapping_mode = "monitor"
        elif self.rb_map_custom.isChecked():
            self._profile.mapping_mode = "custom"
        self._update_monitor_widget()
        self.changed.emit()

    def _on_monitor_combo_changed(self, index: int):
        if self._updating or self._profile is None:
            return
        cur_name = self.combo_monitors.currentData()
        if not cur_name:
            return
        self._profile.selected_monitor = cur_name
        self._profile.mapping_mode = "monitor"
        self._updating = True
        try:
            self.rb_map_mon.setChecked(True)
        finally:
            self._updating = False
        self._update_monitor_widget()
        self.changed.emit()

    def _on_monitor_clicked_on_map(self, monitor_name: str):
        if self._profile is None:
            return
        self._profile.selected_monitor = monitor_name
        self._profile.mapping_mode = "monitor"
        self._updating = True
        try:
            self.rb_map_mon.setChecked(True)
            for i in range(self.combo_monitors.count()):
                if self.combo_monitors.itemData(i) == monitor_name:
                    self.combo_monitors.setCurrentIndex(i)
                    break
        finally:
            self._updating = False
        self._update_monitor_widget()
        self.changed.emit()

    def _on_custom_bounds_changed(self):
        if self._updating or self._profile is None:
            return
        self._profile.custom_bounds = [
            self.spin_cust_x.value(),
            self.spin_cust_y.value(),
            self.spin_cust_w.value(),
            self.spin_cust_h.value(),
        ]
        self.advanced_box.set_summary(
            f"custom bounds: {self.spin_cust_x.value()},{self.spin_cust_y.value()} "
            f"{self.spin_cust_w.value()}x{self.spin_cust_h.value()}"
        )
        self._update_monitor_widget()
        self.changed.emit()

    def _on_aspect_lock_changed(self, checked: bool):
        if self._updating_global:
            return
        self._config.aspect_ratio_lock = checked
        self.changed.emit()

    def _on_aspect_ratio_changed(self, text: str):
        if self._updating_global:
            return
        self._config.tablet_aspect_ratio = text
        self.changed.emit()
