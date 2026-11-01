"""Desktop GUI public API, loaded lazily so painted widgets can share tokens."""

__all__ = ["MainWindow", "ServerWorker", "launch_gui"]


def __getattr__(name):
    if name == "MainWindow":
        from server.gui.main_window import MainWindow
        return MainWindow
    if name == "ServerWorker":
        from server.gui.server_worker import ServerWorker
        return ServerWorker
    if name == "launch_gui":
        from server.gui.app import launch_gui
        return launch_gui
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
