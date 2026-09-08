"""
Active window detection helper for Windows, via ctypes (user32/kernel32).
Mirrors the (app_id, window_title) contract of window_watcher_linux's
get_active_window(): app_id here is the focused window's owning process
executable basename (e.g. "krita.exe"), matched against AppProfile.app_matches
the same way a Linux app_id/WM_CLASS string is.
"""

import ctypes
from ctypes import wintypes
import logging
from typing import Tuple

logger = logging.getLogger("SPenWindowWatcher")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def get_active_window() -> Tuple[str, str]:
    """
    Detect currently focused window application ID and title.
    Returns (app_id, window_title).
    """
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        title = ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        app_id = ""
        if pid.value:
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if hproc:
                try:
                    size = wintypes.DWORD(260)
                    buf = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                        app_id = buf.value.rsplit("\\", 1)[-1]
                finally:
                    kernel32.CloseHandle(hproc)

        return app_id, title
    except Exception as e:
        logger.debug(f"Windows active-window query failed: {e}")
        return "", ""
