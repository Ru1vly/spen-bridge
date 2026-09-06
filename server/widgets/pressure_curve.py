"""
Interactive Pressure Curve visualizer widget using PySide6.
Displays input vs output pressure transfer function with live indicator ball.
"""

import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import QWidget


class PressureCurveWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 200)

        self.curve_type = "linear"
        self.gamma = 1.0
        self.p_min = 0.0
        self.p_max = 1.0
        self.current_pressure = 0.0
        self.calibrated_pressure = 0.0

    def set_params(self, curve_type: str, gamma: float, p_min: float, p_max: float):
        self.curve_type = curve_type
        self.gamma = gamma
        self.p_min = p_min
        self.p_max = p_max
        self.update()

    def set_current_pressure(self, raw_p: float, cal_p: float):
        self.current_pressure = max(0.0, min(1.0, raw_p))
        self.calibrated_pressure = max(0.0, min(1.0, cal_p))
        self.update()

    def calculate_output(self, norm_in: float) -> float:
        """Calculate normalized output (0.0 - 1.0) for a normalized input."""
        if norm_in <= self.p_min:
            return 0.0
        if norm_in >= self.p_max:
            norm = 1.0
        else:
            denom = max(0.001, self.p_max - self.p_min)
            norm = (norm_in - self.p_min) / denom

        norm = max(0.0, min(1.0, norm))

        if self.curve_type == "soft":
            return math.pow(norm, 0.65)
        elif self.curve_type == "firm":
            return math.pow(norm, 1.6)
        elif self.curve_type == "sigmoid":
            return norm * norm * (3.0 - 2.0 * norm)
        elif self.curve_type == "custom":
            gamma = max(0.1, min(5.0, self.gamma))
            return math.pow(norm, gamma)
        else:
            return norm

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        pad_left = 36
        pad_bottom = 26
        pad_top = 16
        pad_right = 16

        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        # Background
        painter.fillRect(self.rect(), QColor("#181825"))

        # Plot area background
        plot_rect = QPointF(pad_left, pad_top)
        painter.fillRect(pad_left, pad_top, plot_w, plot_h, QColor("#1e1e2e"))

        # Grid lines
        grid_pen = QPen(QColor("#313244"), 1, Qt.DashLine)
        painter.setPen(grid_pen)

        for step in (0.25, 0.5, 0.75):
            # Horizontal grid line
            y = pad_top + plot_h * (1.0 - step)
            painter.drawLine(QPointF(pad_left, y), QPointF(pad_left + plot_w, y))

            # Vertical grid line
            x = pad_left + plot_w * step
            painter.drawLine(QPointF(x, pad_top), QPointF(x, pad_top + plot_h))

        # Diagonal baseline (ideal linear reference)
        ref_pen = QPen(QColor("#45475a"), 1, Qt.DotLine)
        painter.setPen(ref_pen)
        painter.drawLine(QPointF(pad_left, pad_top + plot_h), QPointF(pad_left + plot_w, pad_top))

        # Deadzone visual shading
        if self.p_min > 0.0:
            dz_w = plot_w * self.p_min
            painter.fillRect(pad_left, pad_top, dz_w, plot_h, QColor(243, 139, 168, 30))
            dz_pen = QPen(QColor("#f38ba8"), 1, Qt.DashLine)
            painter.setPen(dz_pen)
            painter.drawLine(QPointF(pad_left + dz_w, pad_top), QPointF(pad_left + dz_w, pad_top + plot_h))

        # Ceiling visual line
        if self.p_max < 1.0:
            ceil_x = pad_left + plot_w * self.p_max
            ceil_pen = QPen(QColor("#fab387"), 1, Qt.DashLine)
            painter.setPen(ceil_pen)
            painter.drawLine(QPointF(ceil_x, pad_top), QPointF(ceil_x, pad_top + plot_h))

        # Draw the curve
        path = QPainterPath()
        steps = 60
        for i in range(steps + 1):
            t = i / steps
            out_val = self.calculate_output(t)
            px = pad_left + t * plot_w
            py = pad_top + (1.0 - out_val) * plot_h
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)

        # Draw fill under curve
        fill_path = QPainterPath(path)
        fill_path.lineTo(pad_left + plot_w, pad_top + plot_h)
        fill_path.lineTo(pad_left, pad_top + plot_h)
        fill_path.closeSubpath()
        painter.fillPath(fill_path, QColor(137, 180, 250, 40))

        # Draw curve stroke
        curve_pen = QPen(QColor("#89b4fa"), 2.5)
        painter.setPen(curve_pen)
        painter.drawPath(path)

        # Draw live indicator ball if stylus active
        if self.current_pressure > 0.001:
            out_p = self.calculate_output(self.current_pressure)
            ball_x = pad_left + self.current_pressure * plot_w
            ball_y = pad_top + (1.0 - out_p) * plot_h

            # Outer glow
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(166, 227, 161, 100))
            painter.drawEllipse(QPointF(ball_x, ball_y), 9, 9)

            # Core
            painter.setBrush(QColor("#a6e3a1"))
            painter.drawEllipse(QPointF(ball_x, ball_y), 5, 5)

        # Plot border
        border_pen = QPen(QColor("#585b70"), 1.5)
        painter.setPen(border_pen)
        painter.drawRect(pad_left, pad_top, plot_w, plot_h)

        # Axis labels
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor("#a6adc8"))

        painter.drawText(pad_left, h - 6, "0%")
        painter.drawText(pad_left + plot_w // 2 - 12, h - 6, "Input")
        painter.drawText(pad_left + plot_w - 24, h - 6, "100%")

        painter.drawText(4, pad_top + 10, "100%")
        painter.drawText(8, pad_top + plot_h // 2 + 4, "Out")
        painter.drawText(16, pad_top + plot_h, "0%")
