"""
S Pen Bridge — Desktop GUI package.
Public surface kept identical to the old single-file server/gui.py module:
`from server.gui import launch_gui` and `from server.gui import MainWindow, ServerWorker`.
"""

from server.gui.main_window import MainWindow
from server.gui.server_worker import ServerWorker
from server.gui.app import launch_gui

__all__ = ["MainWindow", "ServerWorker", "launch_gui"]
