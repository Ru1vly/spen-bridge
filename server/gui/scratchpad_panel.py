"""Interactive drawing scratchpad card: color swatches, test-stroke trigger, and the live drawing canvas."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton

from server.widgets.scratchpad import ScratchpadWidget

SWATCH_COLORS = ["#89b4fa", "#cba6f7", "#a6e3a1", "#f9e2af", "#f38ba8", "#ffffff"]


class ScratchpadPanel(QGroupBox):
    test_stroke_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Interactive Scratchpad", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        header = QHBoxLayout()
        for col_hex in SWATCH_COLORS:
            btn_col = QPushButton()
            btn_col.setFixedSize(18, 18)
            btn_col.setStyleSheet(f"background-color: {col_hex}; border-radius: 9px; border: 1px solid #585b70;")
            btn_col.clicked.connect(lambda _checked, c=col_hex: self.scratchpad.set_pen_color(QColor(c)))
            header.addWidget(btn_col)

        header.addStretch()
        btn_synthetic = QPushButton("Test Stroke")
        btn_synthetic.clicked.connect(self._on_test_stroke)
        header.addWidget(btn_synthetic)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.scratchpad.clear_canvas())
        header.addWidget(btn_clear)
        layout.addLayout(header)

        self.scratchpad = ScratchpadWidget()
        self.scratchpad.setMinimumHeight(120)
        layout.addWidget(self.scratchpad, stretch=1)

    def _on_test_stroke(self):
        self.scratchpad.draw_test_spiral()
        self.test_stroke_requested.emit()
