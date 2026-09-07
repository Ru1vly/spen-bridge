"""
Thin persisted-UI-state wrapper (QSettings-backed). Deliberately minimal:
only the last-selected tab and last-edited profile survive a restart.
Everything else (section collapse state, "customized" flags) is recomputed
fresh every time from the live config, so it can never go stale.
"""

from PySide6.QtCore import QSettings


class GuiState:
    def __init__(self):
        self._settings = QSettings("SPenBridge", "S Pen Bridge")

    @property
    def last_tab_index(self) -> int:
        return int(self._settings.value("last_tab_index", 0))

    @last_tab_index.setter
    def last_tab_index(self, value: int):
        self._settings.setValue("last_tab_index", int(value))

    @property
    def last_editing_profile(self) -> str:
        return str(self._settings.value("last_editing_profile", "Default"))

    @last_editing_profile.setter
    def last_editing_profile(self, value: str):
        self._settings.setValue("last_editing_profile", value)
