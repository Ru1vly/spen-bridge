"""
Shared collapsible section widget: a clickable header (chevron + title + a
right-aligned one-line summary that stays visible even while collapsed) above
a body that hides/shows. Used for every "Advanced: ..." sub-section and for
the Server Logs panel: one shared mechanism, no parallel "Card" hierarchy.
"""

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QGroupBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton




class CollapsibleBox(QGroupBox):
    toggled_expanded = Signal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleBox")
        self.setFlat(True)
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QPushButton()
        self._header.setCheckable(True)
        self._header.setAccessibleName(title)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setObjectName("CollapsibleBoxHeader")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)

        self._chevron = QLabel("▸")
        self._chevron.setFixedWidth(12)
        header_layout.addWidget(self._chevron)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-weight: 600;")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        header_layout.addWidget(self._summary_label)

        self._header.toggled.connect(self._on_header_toggled)
        outer.addWidget(self._header)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 4, 8, 8)
        self._body_layout.setSpacing(8)
        outer.addWidget(self._body)

        self.set_expanded(False)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def set_title(self, text: str):
        self._title_label.setText(text)
        self._header.setAccessibleName(text)

    def set_summary(self, text: str):
        self._summary_label.setText(text)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        with QSignalBlocker(self._header):
            self._header.setChecked(expanded)
        self._header.setAccessibleDescription("Expanded" if expanded else "Collapsed")
        self._chevron.setText("▾" if expanded else "▸")
        self._body.setVisible(expanded)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def _on_header_toggled(self, expanded: bool):
        self.set_expanded(expanded)
        self.toggled_expanded.emit(self._expanded)
