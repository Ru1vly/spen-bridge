"""
Selects the OS-appropriate tablet backend at construction time. The concrete
backend module is imported lazily, inside the branch, so merely importing
this module - or anything that imports it, like server.gui - never pulls in
platform-specific dependencies (evdev on Linux, ctypes/WinDLL calls on
Windows) for an OS the process isn't running on.
"""

import platform

from server.backends.base import TabletBackendBase


def create_tablet_backend(**kwargs) -> TabletBackendBase:
    """Construct the tablet backend for the current OS."""
    system = platform.system()
    if system == "Linux":
        from server.backends.linux_uinput import LinuxUinputTablet

        return LinuxUinputTablet(**kwargs)
    elif system == "Windows":
        from server.backends.windows_hid import WindowsHidTablet

        return WindowsHidTablet(**kwargs)
    raise RuntimeError(f"Unsupported platform: {system}")
