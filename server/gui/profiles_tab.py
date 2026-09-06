"""
Profiles tab: the profile list on the left and the full profile editor on
the right, in a resizable splitter. This is the tab that used to be spread
across three separate tabs (Pen & Buttons / Display & Area / Application
Profiles) — everything about one profile is editable from here.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter

from server.config import TabletConfig
from server.gui.server_worker import ServerWorker
from server.gui.profile_list_panel import ProfileListPanel
from server.gui.profile_editor_panel import ProfileEditorPanel


class ProfilesTab(QWidget):
    profile_selected = Signal(str)

    def __init__(self, config: TabletConfig, worker: ServerWorker, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.list_panel = ProfileListPanel(config)
        self.editor_panel = ProfileEditorPanel(config, worker)

        splitter.addWidget(self.list_panel)
        splitter.addWidget(self.editor_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760])

        layout.addWidget(splitter)

        self.list_panel.profile_selected.connect(self.profile_selected.emit)

    def select_profile(self, name: str):
        """Programmatically select a profile in the list — the single public
        entry point used by MainWindow, tests, and internal signal handlers
        alike. Fires through the exact same signal path a user click would."""
        self.list_panel.set_current_by_name(name)
