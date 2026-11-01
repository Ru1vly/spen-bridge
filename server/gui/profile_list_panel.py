"""
Left-hand profile list panel: auto-switch toggle, live focused-window
indicator, the profile list itself (with per-row edit/live/customized
markers), and profile management buttons (new / duplicate / delete).
"""

from server.gui.theme import PALETTE


from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal, QSignalBlocker
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
    QComboBox,
)

from server.config import AppProfile, TabletConfig, get_builtin_default_profiles
from server.gui.widgets.pill_badge import PillBadge


def is_profile_customized(profile: AppProfile) -> bool:
    """A profile is 'customized' if any of its settings fields differ from its
    baseline: neutral dataclass defaults. Application profiles are user-created. Computed fresh every call, never
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
        self._accent_bar.setFixedWidth(0)
        self._accent_bar.setStyleSheet("background: transparent; border-radius: 1px;")
        layout.addWidget(self._accent_bar)

        self._lbl_name = QLabel(name)
        self._lbl_name.setTextFormat(Qt.PlainText)
        self._lbl_name.setStyleSheet("font-weight: 500;")
        layout.addWidget(self._lbl_name, stretch=1)
        if name == "Default":
            self.setToolTip("Global fallback: used when no other profile matches.")

        self._customized_badge = PillBadge("customized", state="customized")
        layout.addWidget(self._customized_badge)
        self._customized_badge.hide()

        self._live_dot = QLabel("●")
        self._live_dot.setStyleSheet(f"color: {PALETTE['green']}; font-size: 13px;")
        layout.addWidget(self._live_dot)
        self._live_dot.hide()

    def set_accent(self, on: bool):
        self._accent_bar.setStyleSheet(f"background: {PALETTE['accent_blue'] if on else 'transparent'}; border-radius: 1px;")

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
        self._outer = layout
        self._compact = False
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chk_auto_switch = QCheckBox("Auto-switch by focused window")
        layout.addWidget(self.chk_auto_switch)

        self.lbl_focused_window = QLabel("Active window: waiting for detection…")
        self.lbl_focused_window.setTextFormat(Qt.PlainText)
        self.lbl_focused_window.setWordWrap(True)
        self.lbl_focused_window.setStyleSheet(
            f"background: {PALETTE['panel']}; color: {PALETTE['accent_blue']}; padding: 4px 8px; border-radius: 6px; font-size: 11px;"
        )
        layout.addWidget(self.lbl_focused_window)

        self.empty_label = QLabel("No app profiles yet. Create a profile to use different pen settings in an app.")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.combo_compact = QComboBox()
        self.combo_compact.setAccessibleName("Profile to edit")
        self.combo_compact.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_compact.setMinimumContentsLength(8)
        self.combo_compact.currentIndexChanged.connect(
            lambda _: self.set_current_by_name(self.combo_compact.currentData()))
        self.combo_compact.hide()
        layout.addWidget(self.combo_compact)

        self.list_widget = QListWidget()
        self.list_widget.setAccessibleName("Profiles")
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        self._button_row = btn_row
        self.btn_new_profile = QPushButton("Create profile")
        btn_row.addWidget(self.btn_new_profile)
        self.btn_duplicate_profile = QPushButton("Duplicate")
        btn_row.addWidget(self.btn_duplicate_profile)
        layout.addLayout(btn_row)

        self.btn_del_prof = QPushButton("Delete profile")
        self.btn_del_prof.setObjectName("dangerBtn")
        layout.addSpacing(16)
        self._delete_gap = layout.itemAt(layout.count() - 1).spacerItem()
        layout.addWidget(self.btn_del_prof)

    def set_compact(self, compact: bool):
        if compact == self._compact:
            return
        self._compact = compact
        self.list_widget.setVisible(not compact)
        self.combo_compact.setVisible(compact)
        if compact:
            self._outer.removeWidget(self.btn_del_prof)
            self._button_row.addSpacing(16)
            self._button_row.addWidget(self.btn_del_prof)
        else:
            self._button_row.removeWidget(self.btn_del_prof)
            self._button_row.takeAt(self._button_row.count() - 1)
            self._outer.addWidget(self.btn_del_prof)
        self._delete_gap.changeSize(0, 0 if compact else 16)
        self._outer.invalidate()

    def _sync_compact(self, name):
        with QSignalBlocker(self.combo_compact):
            self.combo_compact.setCurrentIndex(self.combo_compact.findData(name))
        self.combo_compact.setToolTip(name or "")

    def repopulate(self, active_profile_name: str, editing_profile_name: str):
        self.empty_label.setVisible(not any(name != "Default" for name in self._config.profiles))
        self.combo_compact.blockSignals(True)
        self.combo_compact.clear()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._rows = {}
        self._items = {}
        for name, profile in self._config.profiles.items():
            self.combo_compact.addItem(name, name)
            item = QListWidgetItem(self.list_widget)
            row = ProfileListRow(name)
            item.setSizeHint(row.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            item.setData(Qt.UserRole, name)
            item.setData(Qt.AccessibleTextRole, name)
            self._rows[name] = row
            self._items[name] = item
            row.set_customized(is_profile_customized(profile))
            if name == editing_profile_name:
                self.list_widget.setCurrentItem(item)
        self.list_widget.blockSignals(False)
        self.combo_compact.setCurrentIndex(self.combo_compact.findData(editing_profile_name))
        self.combo_compact.blockSignals(False)
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
            states = []
            if name == editing_profile_name:
                states.append("Editing")
            if auto_switch and name == active_profile_name:
                states.append("Active for input")
            if is_profile_customized(self._config.profiles[name]):
                states.append("Customized")
            self._items[name].setData(Qt.AccessibleDescriptionRole, ", ".join(states))

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
        self._sync_compact(name)
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
            item = self._items[name]
            description = item.data(Qt.AccessibleDescriptionRole) or ""
            states = [state for state in description.split(", ") if state and state != "Customized"]
            if is_profile_customized(profile):
                states.append("Customized")
            item.setData(Qt.AccessibleDescriptionRole, ", ".join(states))

    def selected_profile_name(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_current_item_changed(self, current, previous):
        if current is None:
            return
        name = current.data(Qt.UserRole)
        if name:
            self._sync_compact(name)
            self.profile_selected.emit(name)
