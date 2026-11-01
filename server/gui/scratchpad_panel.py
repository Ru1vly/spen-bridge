"""Interactive drawing scratchpad card: color swatches, test-stroke trigger, and the live drawing canvas."""

from server.gui.theme import PALETTE


from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup

from server.widgets.scratchpad import ScratchpadWidget

SWATCH_ROLES = [("Blue", "accent_blue"), ("Purple", "purple"), ("Green", "green"), ("Amber", "orange"), ("Red", "red"), ("Ink", "text")]


class ScratchpadPanel(QGroupBox):
    test_stroke_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Try your pen", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        header = QVBoxLayout()
        palette_row = QHBoxLayout()
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for index, (name, role) in enumerate(SWATCH_ROLES):
            col_hex = PALETTE[role]
            btn_col = QPushButton()
            btn_col.setFixedSize(28, 28)
            btn_col.setAccessibleName(f"{name} pen color")
            btn_col.setToolTip(name)
            btn_col.setCheckable(True)
            self.color_group.addButton(btn_col)
            btn_col.setChecked(index == 0)
            btn_col.setStyleSheet(
                f"QPushButton {{background-color: {col_hex}; border-radius: 14px; "
                f"border: 3px solid {PALETTE['panel']}; min-height: 20px; min-width: 20px; padding: 0;}}"
                f"QPushButton:checked, QPushButton:focus {{border-color: {PALETTE['text']};}}")
            btn_col.clicked.connect(lambda _checked, c=col_hex: self.scratchpad.set_pen_color(QColor(c)))
            palette_row.addWidget(btn_col)
        palette_row.addStretch()
        header.addLayout(palette_row)
        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_synthetic = btn_synthetic = QPushButton("Test Stroke")
        btn_synthetic.clicked.connect(self._on_test_stroke)
        actions.addWidget(btn_synthetic)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.scratchpad.clear_canvas())
        actions.addWidget(btn_clear)
        header.addLayout(actions)
        layout.addLayout(header)

        self.scratchpad = ScratchpadWidget()
        self.scratchpad.setMinimumHeight(180)
        layout.addWidget(self.scratchpad, stretch=1)

    def _on_test_stroke(self):
        self.scratchpad.draw_test_spiral()
        self.test_stroke_requested.emit()
