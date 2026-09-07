"""
Interactive Drawing Scratchpad widget using PySide6.
Provides an on-screen drawing surface to test S Pen pressure, tilt, and latency in real-time.
"""

import math
from typing import Optional
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QImage, QPaintEvent
from PySide6.QtWidgets import QWidget

from server.protocol import ACTION_DOWN, ACTION_MOVE, ACTION_UP, ACTION_CANCEL


class ScratchpadWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setCursor(Qt.CrossCursor)

        self._pixmap: Optional[QPixmap] = None
        self._last_point: Optional[QPointF] = None
        self._last_pressure: float = 0.5
        self.pen_color = QColor("#89b4fa")  # Soft blue
        self.max_stroke_width = 12.0
        self.min_stroke_width = 1.5

        # Mouse drawing simulation state
        self._mouse_down = False
        # While a real S Pen is connected, the virtual tablet drives the
        # absolute desktop cursor - if that cursor happens to sit over this
        # widget, Qt also delivers it as a genuine mouse press/move here.
        # Left on, that duplicates every stroke: once via add_tablet_point()
        # (using the pen's raw normalized position) and once via the mouse
        # fallback below (using the cursor's actual on-screen position),
        # producing two mismatched drawings for a single pen stroke. So the
        # mouse fallback is only for testing with a literal mouse when no
        # tablet client is connected.
        self._live_input_active = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_size = event.size()
        old_pix = self._pixmap

        new_pix = QPixmap(new_size)
        new_pix.fill(QColor("#11111b"))

        if old_pix is not None:
            painter = QPainter(new_pix)
            painter.drawPixmap(0, 0, old_pix)
            painter.end()

        self._pixmap = new_pix

    def clear_canvas(self):
        """Clear scratchpad to background color."""
        if self._pixmap is not None:
            self._pixmap.fill(QColor("#11111b"))
            self._last_point = None
            self.update()

    def set_pen_color(self, color: QColor):
        self.pen_color = color

    def set_live_input_active(self, active: bool):
        """Toggle whether a real tablet client is feeding add_tablet_point().

        Call with True on client connect and False on disconnect, so the
        mouse fallback below never double-draws alongside live pen events.
        """
        self._live_input_active = active
        if active:
            self._mouse_down = False

    def add_tablet_point(self, norm_x: float, norm_y: float, pressure: float, action: int):
        """
        Feed live tablet event to draw on scratchpad.
        norm_x, norm_y in [0.0, 1.0], pressure in [0.0, 1.0].
        """
        if self._pixmap is None:
            return

        w = self.width()
        h = self.height()
        px = norm_x * w
        py = norm_y * h
        curr_pt = QPointF(px, py)

        if action == ACTION_DOWN:
            self._last_point = curr_pt
            self._last_pressure = pressure
            self._draw_dot(curr_pt, pressure)
        elif action == ACTION_MOVE and pressure > 0.0:
            if self._last_point is not None:
                self._draw_segment(self._last_point, curr_pt, (self._last_pressure + pressure) / 2.0)
            else:
                self._draw_dot(curr_pt, pressure)
            self._last_point = curr_pt
            self._last_pressure = pressure
        elif action in (ACTION_UP, ACTION_CANCEL):
            self._last_point = None

        self.update()

    def _draw_dot(self, pt: QPointF, pressure: float):
        if self._pixmap is None:
            return
        width = self.min_stroke_width + (self.max_stroke_width - self.min_stroke_width) * pressure
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.pen_color)
        painter.drawEllipse(pt, width / 2.0, width / 2.0)
        painter.end()

    def _draw_segment(self, p1: QPointF, p2: QPointF, pressure: float):
        if self._pixmap is None:
            return
        width = self.min_stroke_width + (self.max_stroke_width - self.min_stroke_width) * pressure
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.pen_color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.end()

    def draw_test_spiral(self):
        """Draw a synthetic spiral test on the scratchpad with dynamic pressure."""
        if self._pixmap is None:
            return
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        max_r = min(w, h) * 0.4
        steps = 180
        loops = 3.5

        prev_pt = None
        prev_p = 0.1

        for i in range(steps):
            t = i / steps
            angle = t * loops * 2.0 * math.pi
            r = t * max_r
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            # Sinusoidal pressure curve
            pressure = math.sin(t * math.pi) * 0.85 + 0.15
            pt = QPointF(x, y)
            if prev_pt is not None:
                self._draw_segment(prev_pt, pt, (prev_p + pressure) / 2.0)
            else:
                self._draw_dot(pt, pressure)
            prev_pt = pt
            prev_p = pressure

        self.update()

    # Mouse drawing fallback (only when no live tablet client is connected;
    # see set_live_input_active).
    def mousePressEvent(self, event):
        if not self._live_input_active and event.button() == Qt.LeftButton:
            self._mouse_down = True
            pos = event.position()
            self._last_point = pos
            self._last_pressure = 0.6
            self._draw_dot(pos, 0.6)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._live_input_active and self._mouse_down:
            pos = event.position()
            if self._last_point is not None:
                self._draw_segment(self._last_point, pos, 0.6)
            self._last_point = pos
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._live_input_active and event.button() == Qt.LeftButton:
            self._mouse_down = False
            self._last_point = None
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)
        else:
            painter.fillRect(self.rect(), QColor("#11111b"))

        # Frame border
        border_pen = QPen(QColor("#313244"), 1.5)
        painter.setPen(border_pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Hint text if blank
        painter.setPen(QColor("#45475a"))
        painter.drawText(12, self.height() - 12, "Test Canvas — Draw here with S Pen or mouse")
