"""
Small rounded status pill (colored label) used for every "state" indicator in the GUI:
server status, running/idle badges, live diagnostics badges, and "customized" tags.
Replaces the old pattern of ad hoc setStyleSheet() calls scattered across the code —
this widget just flips a Qt dynamic property; theme.py owns the actual colors.
"""

from PySide6.QtWidgets import QLabel, QWidget


class PillBadge(QLabel):
    def __init__(self, text: str = "", state: str = "idle", parent: QWidget = None):
        super().__init__(text, parent)
        self.setProperty("pillState", state)

    def set_state(self, state: str, text: str = None):
        """state: one of 'ok', 'bad', 'warn', 'idle'."""
        if text is not None:
            self.setText(text)
        if self.property("pillState") != state:
            self.setProperty("pillState", state)
            style = self.style()
            style.unpolish(self)
            style.polish(self)
