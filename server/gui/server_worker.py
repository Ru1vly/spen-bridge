"""
Background asyncio server thread wrapper used by the GUI. Owns the
VirtualTablet + SPenServer lifecycle and exposes Qt signals so MainWindow can
react to status/traffic/pen events without blocking the UI thread.
"""

import asyncio
import logging
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from server.backends.base import TabletBackendBase
from server.backends.factory import create_tablet_backend
from server.config import TabletConfig
from server.monitors import detect_monitors
from server.protocol import PenEvent
from server.server import SPenServer

logger = logging.getLogger("SPenGUI")


class ServerWorker(QObject):
    sig_status = Signal(str, str)             # state ("running", "stopped", "error"), message
    sig_client_connected = Signal(str)        # client address
    sig_client_disconnected = Signal(str)     # client address
    sig_stats = Signal(float, int, int)       # rate, packets, total_events
    sig_pen_event = Signal(object, int, int, int)  # ev, cal_p, abs_x, abs_y
    sig_log = Signal(str)

    def __init__(self, config: TabletConfig):
        super().__init__()
        self.config = config
        self.tablet: Optional[TabletBackendBase] = None
        self.server: Optional[SPenServer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def start_server(self):
        if self._is_running:
            return

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Detect monitors to calculate mapping. Always pass the freshly-detected
        # desktop size too (not just the monitor list) - see
        # get_screen_bounds_and_desktop()'s docstring for why relying on the
        # persisted config.desktop_size alone can silently cut off part of the
        # screen.
        monitors, desk_size = detect_monitors()
        self.config.desktop_size = [desk_size[0], desk_size[1]]
        sb, desk = self.config.get_screen_bounds_and_desktop(monitors, desk_size)

        try:
            self.tablet = create_tablet_backend(
                name=self.config.device_name,
                mode=self.config.device_mode,
                direct_mode=self.config.direct_mode,
                screen_bounds=sb,
                desktop_size=desk,
                click_on_touch=self.config.click_on_touch,
                pressure_curve_type=self.config.pressure_curve_type,
                pressure_gamma=self.config.pressure_gamma,
                pressure_min=self.config.pressure_min,
                pressure_max=self.config.pressure_max,
                stroke_smoothing=self.config.stroke_smoothing,
                button_primary=self.config.button_primary,
                button_secondary=self.config.button_secondary,
                aspect_ratio_lock=self.config.aspect_ratio_lock,
                tablet_aspect_ratio=self.config.tablet_aspect_ratio,
                on_event_processed=self._on_tablet_event,
            )
        except Exception as e:
            self.sig_status.emit("error", f"Failed to create VirtualTablet: {e}")
            return

        self.server = SPenServer(
            tablet=self.tablet,
            host=self.config.host,
            port=self.config.port,
            on_client_connected=lambda c: self.sig_client_connected.emit(c),
            on_client_disconnected=lambda c: self.sig_client_disconnected.emit(c),
            on_stats=lambda r, p, t: self.sig_stats.emit(r, p, t),
        )

        async def _async_start():
            await self.server.start()
            self._is_running = True
            self.sig_status.emit("running", f"Listening on {self.config.host}:{self.config.port}")
            while self._is_running:
                await asyncio.sleep(0.5)
            await self.server.stop()
            self.tablet.close()

        try:
            self._loop.run_until_complete(_async_start())
        except Exception as e:
            self.sig_status.emit("error", f"Server error: {e}")
        finally:
            self._is_running = False
            self.sig_status.emit("stopped", "Server stopped")

    def _on_tablet_event(self, ev: PenEvent, cal_p: int, abs_x: int, abs_y: int):
        self.sig_pen_event.emit(ev, cal_p, abs_x, abs_y)

    def stop_server(self):
        if not self._is_running:
            return
        self._is_running = False

    def update_tablet_settings(self, **kwargs):
        if self.tablet:
            self.tablet.update_settings(**kwargs)

    def set_device_mode(
        self,
        mode: Optional[str] = None,
        direct_mode: Optional[bool] = None,
        device_name: Optional[str] = None,
    ):
        """Hot-swap the virtual tablet device when switching mode, direct mode, or profile."""
        target_mode = mode if mode is not None else self.config.device_mode
        target_direct = direct_mode if direct_mode is not None else self.config.direct_mode
        target_name = device_name if device_name is not None else self.config.device_name

        if (
            self.tablet is not None
            and self.tablet.mode == target_mode
            and self.tablet.direct_mode == target_direct
            and self.tablet.name == target_name
        ):
            return

        if self.tablet is None:
            return

        monitors, desk_size = detect_monitors()
        self.config.desktop_size = [desk_size[0], desk_size[1]]
        sb, desk = self.config.get_screen_bounds_and_desktop(monitors, desk_size)

        try:
            new_tablet = create_tablet_backend(
                name=target_name,
                mode=target_mode,
                direct_mode=target_direct,
                screen_bounds=sb,
                desktop_size=desk,
                click_on_touch=self.config.click_on_touch,
                pressure_curve_type=self.config.pressure_curve_type,
                pressure_gamma=self.config.pressure_gamma,
                pressure_min=self.config.pressure_min,
                pressure_max=self.config.pressure_max,
                stroke_smoothing=self.config.stroke_smoothing,
                button_primary=self.config.button_primary,
                button_secondary=self.config.button_secondary,
                aspect_ratio_lock=self.config.aspect_ratio_lock,
                tablet_aspect_ratio=self.config.tablet_aspect_ratio,
                on_event_processed=self._on_tablet_event,
            )
            old_tablet = self.tablet
            self.tablet = new_tablet
            if self.server:
                self.server.tablet = new_tablet
            if old_tablet:
                old_tablet.close()
            logger.info(f"Hot-swapped VirtualTablet device to mode='{target_mode}', direct_mode={target_direct}")
        except Exception as e:
            logger.error(f"Failed to hot-swap VirtualTablet: {e}")
