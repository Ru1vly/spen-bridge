"""
Match-rule chip editor used by the profile Identity section: each configured
"application match" string (window class / process name substring) renders as
a removable pill, and a MatchChipInput lets the user type new ones. Chips
flip to a green "live match" outline when the currently focused window matches
them (see set_active_window), using the same substring rule as
TabletConfig.find_profile_for_app.
"""

from PySide6.QtCore import Qt, Signal, QRect, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QToolButton,
    QLayout,
    QHBoxLayout,
    QVBoxLayout,
)


class _FlowLayout(QLayout):
    """Lays out child widgets left-to-right, wrapping to a new row when out of horizontal space."""

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()


class MatchChip(QWidget):
    remove_requested = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("MatchChip")
        self._text = text
        self.setProperty("activeMatch", "false")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 6, 3)
        layout.setSpacing(4)

        self._label = QLabel(text)
        layout.addWidget(self._label)

        self._btn_remove = QToolButton()
        self._btn_remove.setText("×")
        self._btn_remove.setAutoRaise(True)
        self._btn_remove.setFixedSize(16, 16)
        self._btn_remove.setCursor(Qt.PointingHandCursor)
        self._btn_remove.clicked.connect(self.remove_requested.emit)
        layout.addWidget(self._btn_remove)

    @property
    def text_value(self) -> str:
        return self._text

    def set_active(self, active: bool):
        state = "true" if active else "false"
        if self.property("activeMatch") != state:
            self.setProperty("activeMatch", state)
            style = self.style()
            style.unpolish(self)
            style.polish(self)


class MatchChipInput(QWidget):
    chips_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._flow_container = QWidget()
        self._flow = _FlowLayout(self._flow_container, margin=0, spacing=6)
        outer.addWidget(self._flow_container)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Type a window name / process, press Enter to add (e.g. krita)")
        self._edit.returnPressed.connect(self._on_return_pressed)
        outer.addWidget(self._edit)

        self._chip_widgets = []

    @property
    def chips(self) -> list:
        return [c.text_value for c in self._chip_widgets]

    def set_chips(self, values):
        for c in list(self._chip_widgets):
            self._flow.removeWidget(c)
            c.deleteLater()
        self._chip_widgets = []
        for v in values:
            v = (v or "").strip()
            if v:
                self._add_chip_widget(v)
        self._flow_container.updateGeometry()

    def add_chip(self, text: str):
        text = (text or "").strip()
        if not text or text in self.chips:
            return
        self._add_chip_widget(text)
        self.chips_changed.emit(self.chips)

    def focus_input(self):
        self._edit.setFocus()

    def _add_chip_widget(self, text: str):
        chip = MatchChip(text)
        chip.remove_requested.connect(lambda c=chip: self._remove_chip(c))
        self._flow.addWidget(chip)
        self._chip_widgets.append(chip)

    def _remove_chip(self, chip: "MatchChip"):
        if chip in self._chip_widgets:
            self._chip_widgets.remove(chip)
            self._flow.removeWidget(chip)
            chip.deleteLater()
            self.chips_changed.emit(self.chips)

    def _on_return_pressed(self):
        text = self._edit.text().strip()
        if text:
            self.add_chip(text)
            self._edit.clear()

    def set_active_window(self, app_id: str, title: str):
        """Mirror TabletConfig.find_profile_for_app's substring rule so the visual
        indicator can never disagree with the real auto-switch matching logic."""
        app_id_l = (app_id or "").lower()
        title_l = (title or "").lower()
        for chip in self._chip_widgets:
            m = chip.text_value.strip().lower()
            active = bool(m) and (m in app_id_l or m in title_l)
            chip.set_active(active)
