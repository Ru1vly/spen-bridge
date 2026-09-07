"""
Left-hand profile list panel: auto-switch toggle, live focused-window
indicator, the profile list itself (with per-row edit/live/customized
markers), and profile management buttons (new / duplicate / delete).
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFrame,
)

from server.config import AppProfile, TabletConfig, get_builtin_default_profiles
from server.gui.widgets.pill_badge import PillBadge


def is_profile_customized(profile: AppProfile) -> bool:
    """A profile is 'customized' if any of its settings fields differ from its
    baseline: the matching built-in preset for one of the four shipped names,
    or plain dataclass defaults otherwise. Computed fresh every call, never
    persisted, so it's always correct for whatever the profile currently holds."""
    baseline = get_builtin_default_profiles().get(profile.name)
    if baseline is None:
        baseline = AppProfile(name=profile.name, app_matches=profile.app_matches)
    for f in AppProfile.__dataclass_fields__.values():
        if f.name in ("name", "app_matches"):
            continue
        if getattr(profile, f.name) != getattr(baseline, f.name):
            return True
    return False


class ProfileListRow(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 8, 6)
        layout.setSpacing(8)

        self._accent_bar = QFrame()
        self._accent_bar.setFixedWidth(3)
        self._accent_bar.setStyleSheet("background: transparent; border-radius: 1px;")
        layout.addWidget(self._accent_bar)

        self._lbl_name = QLabel(name)
        self._lbl_name.setStyleSheet("font-weight: 500;")
        layout.addWidget(self._lbl_name, stretch=1)
        if name == "Default":
            self.setToolTip("Global fallback: used when no other profile matches.")

        self._customized_badge = PillBadge("customized", state="customized")
        layout.addWidget(self._customized_badge)
        self._customized_badge.hide()

        self._live_dot = QLabel("●")
        self._live_dot.setStyleSheet("color: #a6e3a1; font-size: 13px;")
        layout.addWidget(self._live_dot)
        self._live_dot.hide()

    def set_accent(self, on: bool):
        self._accent_bar.setStyleSheet(f"background: {'#89b4fa' if on else 'transparent'}; border-radius: 1px;")

    def set_live(self, on: bool):
        self._live_dot.setVisible(on)

    def set_customized(self, on: bool):
        self._customized_badge.setVisible(on)


class ProfileListPanel(QWidget):
    profile_selected = Signal(str)

    def __init__(self, config: TabletConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._rows: Dict[str, ProfileListRow] = {}
        self._items: Dict[str, QListWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chk_auto_switch = QCheckBox("Auto-switch by focused window")
        layout.addWidget(self.chk_auto_switch)

        self.lbl_focused_window = QLabel("Active Window: Detecting...")
        self.lbl_focused_window.setWordWrap(True)
        self.lbl_focused_window.setStyleSheet(
            "background: #181825; color: #89b4fa; padding: 4px 8px; border-radius: 6px; font-size: 11px;"
        )
        layout.addWidget(self.lbl_focused_window)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_new_profile = QPushButton("+ New")
        btn_row.addWidget(self.btn_new_profile)
        self.btn_duplicate_profile = QPushButton("Duplicate")
        btn_row.addWidget(self.btn_duplicate_profile)
        layout.addLayout(btn_row)

        self.btn_del_prof = QPushButton("Delete")
        layout.addWidget(self.btn_del_prof)

    def repopulate(self, active_profile_name: str, editing_profile_name: str):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._rows = {}
        self._items = {}
        for name, profile in self._config.profiles.items():
            item = QListWidgetItem(self.list_widget)
            row = ProfileListRow(name)
            item.setSizeHint(row.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            item.setData(Qt.UserRole, name)
            self._rows[name] = row
            self._items[name] = item
            row.set_customized(is_profile_customized(profile))
            if name == editing_profile_name:
                self.list_widget.setCurrentItem(item)
        self.list_widget.blockSignals(False)
        self.refresh_markers(active_profile_name, editing_profile_name)

        can_delete = editing_profile_name != "Default"
        self.btn_del_prof.setEnabled(can_delete)
        self.btn_del_prof.setToolTip(
            ""
            if can_delete
            else "The Default profile cannot be deleted: it is the fallback used when no other profile matches."
        )

    def refresh_markers(self, active_profile_name: str, editing_profile_name: str):
        auto_switch = self._config.auto_switch_profiles
        for name, row in self._rows.items():
            row.set_accent(name == editing_profile_name)
            row.set_live(auto_switch and name == active_profile_name)

    def set_current_by_name(self, name: str):
        """Select a row AND fire profile_selected: the entry point for
        actions that need the full selection-change chain to run (new/
        duplicate/delete, tests, ProfilesTab.select_profile)."""
        item = self._items.get(name)
        if item is not None:
            self.list_widget.setCurrentItem(item)

    def sync_current_by_name(self, name: str):
        """Update which row is highlighted WITHOUT emitting profile_selected:
        used when the selection change already originated elsewhere (e.g. the
        header combo) and the list just needs to visually agree, without
        re-entering the selection-change handling a second time."""
        item = self._items.get(name)
        if item is not None and self.list_widget.currentItem() is not item:
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentItem(item)
            self.list_widget.blockSignals(False)

    def refresh_customized_badge(self, name: str):
        """Recompute one row's 'customized' badge: call this whenever the
        currently-edited profile's settings change, since editing a profile
        in place doesn't otherwise trigger a full repopulate()."""
        row = self._rows.get(name)
        profile = self._config.profiles.get(name)
        if row is not None and profile is not None:
            row.set_customized(is_profile_customized(profile))

    def selected_profile_name(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_current_item_changed(self, current, previous):
        if current is None:
            return
        name = current.data(Qt.UserRole)
        if name:
            self.profile_selected.emit(name)
