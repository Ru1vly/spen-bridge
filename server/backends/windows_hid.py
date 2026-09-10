"""Windows Ink tablet backed by the SPen KMDF/VHF driver."""
import logging
import math
import threading

from server.backends.base import TabletBackendBase
from server.backends.windows_report import (
    pack_pen, pack_mouse, TIP, BARREL, IN_RANGE, INVERT, ERASER,
)
from server.backends.windows_transport import DriverConnection
from server.protocol import (
    ACTION_DOWN, ACTION_MOVE, ACTION_UP, ACTION_CANCEL, ACTION_HOVER_ENTER,
    ACTION_HOVER_MOVE, ACTION_HOVER_EXIT, TOOL_STYLUS, TOOL_ERASER,
    BUTTON_STYLUS, BUTTON_STYLUS2,
)

logger = logging.getLogger("SPenTablet")


class WindowsHidTablet(TabletBackendBase):
    COORD_MAX = PRESSURE_MAX = 32767

    def __init__(self, **kwargs):
        self._lock = threading.RLock()
        self._connection = None
        self._smooth = None
        self._position = (0, 0)
        self._flags = 0
        self._mouse_buttons = 0
        super().__init__(**kwargs)

    def _setup_device(self):
        self._connection = DriverConnection()
        logger.info("Connected to S Pen virtual HID driver (Windows Ink)")

    def update_settings(self, **kwargs):
        with self._lock:
            # Release existing mappings before assigning a new action.
            if any(k in kwargs and kwargs[k] != getattr(self, k)
                   for k in ("button_primary", "button_secondary")):
                self.reset()
            super().update_settings(**kwargs)

    def handle_event(self, ev):
        with self._lock:
            if self._connection is None:
                return
            if ev.tool_type not in (TOOL_STYLUS, TOOL_ERASER):
                return
            if ev.action not in range(7) or not all(math.isfinite(v) for v in
                    (ev.x, ev.y, ev.pressure, ev.tilt_x, ev.tilt_y)):
                return
            if ev.action in (ACTION_CANCEL, ACTION_HOVER_EXIT):
                self.reset()
                return
            x, y = ev.x, ev.y
            if ev.action == ACTION_MOVE and self._smooth is not None:
                s = self.stroke_smoothing
                x, y = x * (1 - s) + self._smooth[0] * s, y * (1 - s) + self._smooth[1] * s
            self._smooth = (x, y) if ev.action != ACTION_UP else None
            self._position = self._map_coordinates(x, y)
            contact = ev.action in (ACTION_DOWN, ACTION_MOVE) and self.click_on_touch
            pressure = self.calibrate_pressure(ev.pressure) if contact else 0
            if contact and ev.action == ACTION_DOWN:
                pressure = max(1, pressure)
            flags = IN_RANGE
            if ev.tool_type == TOOL_ERASER:
                flags |= INVERT
                if contact:
                    flags |= ERASER
            elif contact:
                flags |= TIP
            mouse = 0
            for mask, action in ((BUTTON_STYLUS, self.button_primary),
                                 (BUTTON_STYLUS2, self.button_secondary)):
                if ev.buttons & mask:
                    if action == "right_click":
                        flags |= BARREL
                    else:
                        mouse |= {"left_click": 1, "middle_click": 4}.get(action, 0)
            self._connection.submit(pack_pen(flags, *self._position, pressure, ev.tilt_x, ev.tilt_y))
            if mouse != self._mouse_buttons:
                self._connection.submit(pack_mouse(mouse))
            self._flags, self._mouse_buttons, self._is_down = flags, mouse, contact
            if self.on_event_processed:
                try:
                    self.on_event_processed(ev, pressure, *self._position)
                except Exception:
                    logger.debug("Pen monitoring callback failed", exc_info=True)

    def _release_touch(self):
        with self._lock:
            self._flags &= ~(TIP | ERASER)
            if self._connection is not None:
                self._connection.submit(pack_pen(self._flags, *self._position))
            self._is_down = False

    def reset(self):
        """Release proximity and buttons while retaining the open driver handle."""
        with self._lock:
            if self._connection is not None:
                self._connection.submit(pack_pen(0, *self._position))
                self._connection.submit(pack_mouse())
            self._flags = self._mouse_buttons = 0
            self._is_down = False
            self._smooth = None

    def close(self):
        with self._lock:
            if self._connection is not None:
                try:
                    self.reset()
                except OSError as error:
                    logger.warning("Unable to submit final HID release: %s", error)
                finally:
                    self._connection.close()
                    self._connection = None
