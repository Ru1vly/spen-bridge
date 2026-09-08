"""
Cross-platform active-window watcher. `get_active_window()` is resolved once
at import time from the OS-appropriate implementation
(window_watcher_linux / window_watcher_windows), then polled on a background
thread by WindowWatcher, which fires a callback when the focused app changes.
"""

import logging
import sys
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger("SPenWindowWatcher")

if sys.platform == "win32":
    from server.window_watcher_windows import get_active_window
else:
    from server.window_watcher_linux import get_active_window

__all__ = ["get_active_window", "WindowWatcher"]


class WindowWatcher:
    """Monitors the active window and triggers a callback when the focused app changes."""

    def __init__(self, callback: Optional[Callable[[str, str], None]] = None, poll_interval: float = 0.3):
        self.callback = callback
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_app_id = ""
        self.last_title = ""

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                app_id, title = get_active_window()
                if (app_id != self.last_app_id or title != self.last_title) and (app_id or title):
                    self.last_app_id = app_id
                    self.last_title = title
                    if self.callback:
                        self.callback(app_id, title)
            except Exception as e:
                logger.debug(f"Window watcher loop error: {e}")
            time.sleep(self.poll_interval)
