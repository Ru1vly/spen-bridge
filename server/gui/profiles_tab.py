"""Pen tuning and profile management share one authoritative profile editor."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QComboBox, QPushButton
from server.config import TabletConfig
from server.gui.server_worker import ServerWorker
from server.gui.profile_list_panel import ProfileListPanel
from server.gui.profile_editor_panel import ProfileEditorPanel


class ProfilesTab(QWidget):
    profile_selected = Signal(str)
    manage_requested = Signal()

    def __init__(self, config: TabletConfig, worker: ServerWorker, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        title = QLabel("Pen settings")
        title.setObjectName("workspaceTitle")
        layout.addWidget(title)
        context = QHBoxLayout()
        context.addWidget(QLabel("Editing:"))
        self.edit_selector = QComboBox()
        self.edit_selector.setAccessibleName("Profile to tune")
        self.edit_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.edit_selector.setMinimumContentsLength(8)
        self.edit_selector.currentIndexChanged.connect(lambda _: self.select_profile(self.edit_selector.currentData()))
        context.addWidget(self.edit_selector, 1)
        manage = QPushButton("Manage profiles")
        manage.clicked.connect(self.manage_requested.emit)
        context.addWidget(manage)
        layout.addLayout(context)
        self.list_panel = ProfileListPanel(config)
        self.editor_panel = ProfileEditorPanel(config, worker)
        layout.addWidget(self.editor_panel, 1)
        self.list_panel.profile_selected.connect(self.profile_selected.emit)

    def populate(self, names, selected):
        with QSignalBlocker(self.edit_selector):
            self.edit_selector.clear()
            for name in names:
                self.edit_selector.addItem(name, name)
            self.edit_selector.setCurrentIndex(self.edit_selector.findData(selected))

    def sync_selection(self, name):
        with QSignalBlocker(self.edit_selector):
            self.edit_selector.setCurrentIndex(self.edit_selector.findData(name))

    def select_profile(self, name: str):
        self.list_panel.set_current_by_name(name)


class ProfileManager(QWidget):
    tune_requested = Signal()
    def __init__(self, pen_page, parent=None):
        super().__init__(parent)
        self.pen_page = pen_page
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        title = QLabel("App profiles")
        title.setObjectName("workspaceTitle")
        outer.addWidget(title)
        hint = QLabel("Choose a profile, then set which apps activate it. Tune its pen behavior in Pen settings.")
        hint.setWordWrap(True)
        hint.setObjectName("supportingText")
        outer.addWidget(hint)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(pen_page.list_panel)
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(pen_page.editor_panel.identity_section)
        tune = QPushButton("Tune selected profile")
        tune.setObjectName("primaryBtn")
        tune.clicked.connect(self.tune_requested.emit)
        self.tune_button = tune
        detail_layout.addWidget(tune)
        detail_layout.addStretch()
        self.splitter.addWidget(details)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)
        self._compact = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < self.fontMetrics().horizontalAdvance("M") * 60
        if self._compact == compact:
            return
        self._compact = compact
        panel = self.pen_page.list_panel
        panel.setMaximumHeight(16777215)
        panel.set_compact(compact)
        self.splitter.setOrientation(Qt.Vertical if compact else Qt.Horizontal)
        if compact:
            panel.layout().activate()
            height = panel.sizeHint().height()
            panel.setMaximumHeight(height)
            self.splitter.setSizes([height, 800])
        else:
            self.splitter.setSizes([260, 700])
