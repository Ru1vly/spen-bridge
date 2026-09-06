"""
System & Diagnostics tab: connection/pairing + startup preferences on the
left, live diagnostics + scratchpad + logs on the right.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea

from server.config import TabletConfig
from server.gui.connection_panel import ConnectionPanel
from server.gui.startup_panel import StartupPanel
from server.gui.diagnostics_panel import DiagnosticsCard
from server.gui.scratchpad_panel import ScratchpadPanel
from server.gui.log_panel import LogPanel


class SystemTab(QWidget):
    def __init__(self, local_ip: str, config: TabletConfig, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Left column: connection + startup
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)

        self.connection_panel = ConnectionPanel(local_ip, config)
        left_layout.addWidget(self.connection_panel)

        self.startup_panel = StartupPanel(config)
        left_layout.addWidget(self.startup_panel)
        left_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_content)
        layout.addWidget(left_scroll, stretch=5)

        # Right column: diagnostics + scratchpad + logs
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        self.diagnostics_panel = DiagnosticsCard()
        right_layout.addWidget(self.diagnostics_panel)

        self.scratchpad_panel = ScratchpadPanel()
        right_layout.addWidget(self.scratchpad_panel, stretch=1)

        self.log_panel = LogPanel()
        right_layout.addWidget(self.log_panel)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_content)
        layout.addWidget(right_scroll, stretch=6)

        self.startup_panel.port_changed.connect(self.connection_panel.on_port_changed)
        self.connection_panel.log_message.connect(self.log_panel.log)
