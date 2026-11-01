"""Connection workspace with optional input diagnostics."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from server.config import TabletConfig
from server.gui.connection_panel import ConnectionPanel
from server.gui.startup_panel import StartupPanel
from server.gui.diagnostics_panel import DiagnosticsCard
from server.gui.log_panel import LogPanel
from server.gui.widgets.collapsible_box import CollapsibleBox


class SystemTab(QWidget):
    def __init__(self, local_ip: str, config: TabletConfig, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Connection")
        title.setObjectName("workspaceTitle")
        outer.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(16)
        self.connection_panel = ConnectionPanel(local_ip, config)
        self.startup_panel = StartupPanel(config)
        self.log_panel = LogPanel()
        layout.addWidget(self.connection_panel)
        self.details = CollapsibleBox("Connection details")
        self.diagnostics_panel = DiagnosticsCard()
        self.details.body_layout().addWidget(self.diagnostics_panel)
        layout.addWidget(self.details)
        layout.addStretch()
        self.scroll.setWidget(content)
        self.startup_panel.changed.connect(self.connection_panel.refresh_ip_label)
        self.startup_panel.port_changed.connect(self.connection_panel.on_port_changed)
        self.connection_panel.log_message.connect(self.log_panel.log)
