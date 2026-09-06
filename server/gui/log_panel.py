"""Collapsible server log panel — collapsed by default, summary always visible."""

import time

from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QTextEdit

from server.gui.widgets.collapsible_box import CollapsibleBox


class LogPanel(CollapsibleBox):
    def __init__(self, parent=None):
        super().__init__("Server Logs", parent)
        self._line_count = 0

        header_row = QHBoxLayout()
        header_row.addStretch()
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text_logs.toPlainText()))
        header_row.addWidget(btn_copy)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._on_clear)
        header_row.addWidget(btn_clear)
        self.body_layout().addLayout(header_row)

        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        self.text_logs.setMaximumHeight(160)
        self.body_layout().addWidget(self.text_logs)

        self.set_summary("0 lines")

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.text_logs.append(f"[{timestamp}] {message}")
        self._line_count += 1
        self.set_summary(f"{self._line_count} line{'s' if self._line_count != 1 else ''}")

    def _on_clear(self):
        self.text_logs.clear()
        self._line_count = 0
        self.set_summary("0 lines")
