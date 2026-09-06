"""
Interactive Monitor Layout visualization widget using PySide6.
Draws detected monitors in their desktop coordinate arrangement and allows click selection.
"""

from typing import List, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget


class MonitorLayoutWidget(QWidget):
    monitor_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 180)
        self.setCursor(Qt.PointingHandCursor)

        self.monitors: List[Dict[str, Any]] = []
        self.desktop_width = 1920
        self.desktop_height = 1080
        self.mapping_mode = "all"  # "all", "monitor", "custom"
        self.selected_monitor = ""
        self.custom_bounds = (0, 0, 1920, 1080)

        # Mapping from monitor name to widget screen rect for hit testing
        self._screen_rects: Dict[str, QRectF] = {}

    def set_data(
        self,
        monitors: List[Dict[str, Any]],
        desktop_size: tuple,
        mapping_mode: str,
        selected_monitor: str,
        custom_bounds: Optional[tuple] = None,
    ):
        self.monitors = monitors
        self.desktop_width = max(100, desktop_size[0])
        self.desktop_height = max(100, desktop_size[1])
        self.mapping_mode = mapping_mode
        self.selected_monitor = selected_monitor
        if custom_bounds:
            self.custom_bounds = custom_bounds
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            for name, rect in self._screen_rects.items():
                if rect.contains(pos):
                    self.monitor_clicked.emit(name)
                    break
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Canvas background
        painter.fillRect(self.rect(), QColor("#181825"))

        pad = 20
        avail_w = w - pad * 2
        avail_h = h - pad * 2

        # Scale factor to fit full desktop inside widget
        scale_x = avail_w / self.desktop_width
        scale_y = avail_h / self.desktop_height
        scale = min(scale_x, scale_y)

        draw_w = self.desktop_width * scale
        draw_h = self.desktop_height * scale
        offset_x = pad + (avail_w - draw_w) / 2
        offset_y = pad + (avail_h - draw_h) / 2

        self._screen_rects.clear()

        # Draw full desktop boundary outline
        desk_pen = QPen(QColor("#313244"), 1, Qt.DashLine)
        painter.setPen(desk_pen)
        painter.drawRect(QRectF(offset_x, offset_y, draw_w, draw_h))

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        # Draw each monitor
        for mon in self.monitors:
            mx = offset_x + mon["x"] * scale
            my = offset_y + mon["y"] * scale
            mw = mon["width"] * scale
            mh = mon["height"] * scale
            mrect = QRectF(mx, my, mw, mh)
            self._screen_rects[mon["name"]] = mrect

            is_selected = (
                (self.mapping_mode == "all") or
                (self.mapping_mode == "monitor" and mon["name"] == self.selected_monitor)
            )

            if is_selected:
                fill_color = QColor(137, 180, 250, 45)
                border_color = QColor("#89b4fa")
                border_width = 2.5
            else:
                fill_color = QColor(69, 71, 90, 40)
                border_color = QColor("#585b70")
                border_width = 1.0

            painter.fillRect(mrect, fill_color)
            painter.setPen(QPen(border_color, border_width))
            painter.drawRoundedRect(mrect, 4, 4)

            # Monitor text label
            painter.setPen(QColor("#cdd6f4") if is_selected else QColor("#a6adc8"))
            info_text = f"{mon['name']}\n{mon['width']}x{mon['height']}"
            painter.drawText(mrect, Qt.AlignCenter, info_text)

        # If custom bounds mode, draw custom highlighted rectangle
        if self.mapping_mode == "custom" and len(self.custom_bounds) == 4:
            cx, cy, cw, ch = self.custom_bounds
            rcx = offset_x + cx * scale
            rcy = offset_y + cy * scale
            rcw = cw * scale
            rch = ch * scale
            crect = QRectF(rcx, rcy, rcw, rch)

            painter.fillRect(crect, QColor(166, 227, 161, 50))
            painter.setPen(QPen(QColor("#a6e3a1"), 2, Qt.DashLine))
            painter.drawRoundedRect(crect, 4, 4)
            painter.setPen(QColor("#a6e3a1"))
            painter.drawText(crect, Qt.AlignTop | Qt.AlignLeft, " Custom Region")
