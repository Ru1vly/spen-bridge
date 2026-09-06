"""
Live S Pen input diagnostics card: pressure/position/tilt readouts, traffic
rate, and hover/touch/barrel/eraser/click status badges.
"""

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QProgressBar

from server.gui.widgets.pill_badge import PillBadge


class DiagnosticsCard(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Live S Pen Input Diagnostics", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.lbl_pressure_diag = QLabel("Pressure: 0 / 4095 (0%)")
        layout.addWidget(self.lbl_pressure_diag)

        self.bar_pressure = QProgressBar()
        self.bar_pressure.setRange(0, 4095)
        layout.addWidget(self.bar_pressure)

        coords_layout = QGridLayout()
        coords_layout.addWidget(QLabel("Position:"), 0, 0)
        self.lbl_pos_val = QLabel("0.000, 0.000")
        self.lbl_pos_val.setStyleSheet("font-weight: bold; color: #89b4fa;")
        coords_layout.addWidget(self.lbl_pos_val, 0, 1)

        coords_layout.addWidget(QLabel("Tilt:"), 0, 2)
        self.lbl_tilt_val = QLabel("0.0°, 0.0°")
        coords_layout.addWidget(self.lbl_tilt_val, 0, 3)

        coords_layout.addWidget(QLabel("Traffic:"), 1, 0)
        self.lbl_traffic_val = QLabel("0 events/sec")
        coords_layout.addWidget(self.lbl_traffic_val, 1, 1)
        layout.addLayout(coords_layout)

        badges_layout = QHBoxLayout()
        self.badge_hover = PillBadge("Hover", state="idle")
        self.badge_touch = PillBadge("Touch", state="idle")
        self.badge_barrel = PillBadge("Barrel Btn", state="idle")
        self.badge_eraser = PillBadge("Eraser", state="idle")
        self.badge_click = PillBadge("Click: ON", state="ok")
        for b in (self.badge_hover, self.badge_touch, self.badge_barrel, self.badge_eraser, self.badge_click):
            badges_layout.addWidget(b)
        layout.addLayout(badges_layout)

    def update_pen_event(self, ev, cal_p: int, abs_x: int, abs_y: int):
        pct = int((cal_p / 4095.0) * 100)
        self.bar_pressure.setValue(cal_p)
        self.lbl_pressure_diag.setText(f"Pressure: {cal_p} / 4095 ({pct}%)")
        self.lbl_pos_val.setText(f"{ev.x:.3f}, {ev.y:.3f}  ({abs_x}, {abs_y})")
        self.lbl_tilt_val.setText(f"{ev.tilt_x:.1f}°, {ev.tilt_y:.1f}°")

        is_hover = ev.action in (0, 1)
        is_down = ev.action in (3, 4)
        has_barrel = bool(ev.buttons & 1)

        self.badge_hover.set_state("ok" if is_hover else "idle")
        self.badge_touch.set_state("ok" if is_down else "idle")
        self.badge_barrel.set_state("warn" if has_barrel else "idle")

    def update_traffic(self, rate: float, packets: int):
        self.lbl_traffic_val.setText(f"{rate:.1f} events/sec ({packets} pkts)")

    def set_click_on_touch(self, enabled: bool):
        self.badge_click.set_state("ok" if enabled else "bad", "Click: ON" if enabled else "Click: OFF")
