"""System tray icon + menu (Show Dashboard / Toggle Server / Quit)."""

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


class SystemTrayController:
    def __init__(self, window, icon_path: Path):
        self.window = window
        self.tray_icon = QSystemTrayIcon(window)
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(window.style().standardIcon(window.style().StandardPixmap.SP_ComputerIcon))

        menu = QMenu()
        act_show = menu.addAction("Show Dashboard")
        act_show.triggered.connect(self.show_and_activate)

        menu.addSeparator()

        self.act_toggle = menu.addAction("Start Server")
        self.act_toggle.triggered.connect(window.toggle_server)

        menu.addSeparator()

        act_quit = menu.addAction("Quit")
        act_quit.triggered.connect(window.force_quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_activated)
        self.tray_icon.show()

    def show_and_activate(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def notify(self, title: str, message: str):
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 2000)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.show_and_activate()
