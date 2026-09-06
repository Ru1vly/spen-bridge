"""
The full editor for whichever profile is currently selected: stacks the 5
profile sections (identity, device, pressure, buttons, mapping) in one
scrollable page, and pushes live edits to the running ServerWorker whenever
the profile being edited is also the currently active (live) one.
"""

from typing import Optional

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea

from server.config import AppProfile, TabletConfig
from server.gui.server_worker import ServerWorker
from server.gui.profile_sections.identity_section import IdentitySection
from server.gui.profile_sections.device_section import DeviceSection
from server.gui.profile_sections.pressure_section import PressureSection
from server.gui.profile_sections.buttons_section import ButtonsSection
from server.gui.profile_sections.mapping_section import MappingSection

LIVE_APPLY_DEBOUNCE_MS = 80


class ProfileEditorPanel(QWidget):
    profile_dirty = Signal()

    def __init__(self, config: TabletConfig, worker: ServerWorker, parent=None):
        super().__init__(parent)
        self._config = config
        self._worker = worker
        self._profile: Optional[AppProfile] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(16)

        self.identity_section = IdentitySection()
        self.device_section = DeviceSection()
        self.pressure_section = PressureSection()
        self.buttons_section = ButtonsSection()
        self.mapping_section = MappingSection(config)

        for section in (
            self.identity_section,
            self.device_section,
            self.pressure_section,
            self.buttons_section,
            self.mapping_section,
        ):
            content_layout.addWidget(section)
            section.changed.connect(self._on_section_changed)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._push_timer = QTimer(self)
        self._push_timer.setSingleShot(True)
        self._push_timer.setInterval(LIVE_APPLY_DEBOUNCE_MS)
        self._push_timer.timeout.connect(self._push_live_settings)

    def bind_profile(self, profile: AppProfile):
        """Re-populate every section's existing widgets from `profile` in place
        (blockSignals-guarded inside each section's set_profile) — never
        destroys/recreates widgets, so scroll position is preserved."""
        self._push_timer.stop()
        self._profile = profile
        self.identity_section.set_profile(profile)
        self.device_section.set_profile(profile)
        self.pressure_section.set_profile(profile)
        self.buttons_section.set_profile(profile)
        self.mapping_section.set_profile(profile)

    @property
    def current_profile_name(self) -> str:
        return self._profile.name if self._profile is not None else ""

    def update_live_match(self, app_id: str, title: str):
        self.identity_section.update_live_match(app_id, title)

    def _on_section_changed(self):
        self._push_timer.start()
        self.profile_dirty.emit()

    def _push_live_settings(self):
        """Push the bound profile's settings to the live VirtualTablet — but only
        if it's actually the profile currently driving the device. Re-checked at
        fire time (not cached at edit time), so this is a no-op if auto-switch
        moved the active profile elsewhere mid-edit."""
        profile = self._profile
        if profile is None or profile.name != self._config.active_profile_name:
            return
        self._worker.set_device_mode(
            mode=profile.device_mode,
            direct_mode=profile.direct_mode,
            device_name=self._config.device_name,
        )
        sb, desk = self._config.get_screen_bounds_and_desktop(
            self.mapping_section.monitors, self.mapping_section.desktop_size
        )
        self._worker.update_tablet_settings(
            click_on_touch=profile.click_on_touch,
            pressure_curve_type=profile.pressure_curve_type,
            pressure_gamma=profile.pressure_gamma,
            pressure_min=profile.pressure_min,
            pressure_max=profile.pressure_max,
            stroke_smoothing=profile.stroke_smoothing,
            button_primary=profile.button_primary,
            button_secondary=profile.button_secondary,
            screen_bounds=sb,
            desktop_size=desk,
        )
