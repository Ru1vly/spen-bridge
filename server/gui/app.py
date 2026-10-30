"""Application entry point for the S Pen Bridge desktop GUI."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from server.gui.main_window import MainWindow


def launch_gui():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("S Pen Bridge")
    app.setOrganizationName("SPenOnLinux")

    window = MainWindow()
    app.aboutToQuit.connect(window.worker.shutdown)
    app.aboutToQuit.connect(window.system_tab.connection_panel.stop_usb_monitor)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
