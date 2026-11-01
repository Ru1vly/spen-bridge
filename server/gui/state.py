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
        try:
            current = self._settings.value("last_workspace_index", None)
            if current is None:
                old = int(self._settings.value("last_tab_index", 1))
                return 1 if old == 0 else 0
            index = int(current)
        except (ValueError, TypeError):
            return 0
        return index if index in (0, 1, 2, 3) else 0

    @last_tab_index.setter
    def last_tab_index(self, value: int):
        self._settings.setValue("last_workspace_index", int(value))

    @property
    def last_editing_profile(self) -> str:
        return str(self._settings.value("last_editing_profile", "Default"))

    @last_editing_profile.setter
    def last_editing_profile(self, value: str):
        self._settings.setValue("last_editing_profile", value)
