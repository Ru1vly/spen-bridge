"""
Virtual Drawing Tablet implementation using Linux uinput via python-evdev.
Supports both "pointer" mode (absolute mouse/pointer for compositors like driftwm, sway, GNOME, KDE)
and "tablet" mode (pure Wacom tablet tool for tablet-v2 compositors).

This is the only module in the repository allowed to `import evdev` - keeping
that import confined here (rather than at server.backends package level) is
what lets the rest of the app, including server.gui, be imported on Windows
before a real Windows backend exists (see server.backends.factory).
"""

import logging
import time
from typing import Optional

import evdev
from evdev import ecodes as e

from server.backends.base import (
    ABS_MAX_COORDINATE,
    ABS_MAX_PRESSURE,
    TILT_MIN,
    TILT_MAX,
    TabletBackendBase,
)
from server.protocol import (
    PenEvent,
    ACTION_HOVER_MOVE,
    ACTION_HOVER_ENTER,
    ACTION_HOVER_EXIT,
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    ACTION_CANCEL,
    TOOL_STYLUS,
    TOOL_ERASER,
    BUTTON_STYLUS,
    BUTTON_STYLUS2,
)

logger = logging.getLogger("SPenTablet")


class LinuxUinputTablet(TabletBackendBase):
    """Emulates a drawing tablet / pointer via /dev/uinput."""

    def __init__(self, **kwargs):
        self.uinput: Optional[evdev.UInput] = None
        self._is_in_proximity = False
        self._active_tool = TOOL_STYLUS
        self._button_stylus_pressed = False
        self._button_stylus2_pressed = False

        # Smoothing state
        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None

        super().__init__(**kwargs)

    def _setup_device(self):
        """Register device capabilities with the Linux uinput kernel driver."""
        if self.mode == "tablet":
            key_codes = [
                e.BTN_TOOL_PEN,
                e.BTN_TOOL_RUBBER,
                e.BTN_TOUCH,
                e.BTN_STYLUS,
                e.BTN_STYLUS2,
            ]
        else:
            # Pointer / Digitizer mode (dispatches PointerMotionAbsolute & PointerButton in Smithay / driftwm / Wayland)
            # CRITICAL: Do NOT add BTN_TOOL_PEN here! Libinput classifies devices with BTN_TOOL_PEN
            # as graphics tablet tools instead of absolute desktop pointers, disabling the desktop cursor.
            key_codes = [
                e.BTN_LEFT,
                e.BTN_RIGHT,
                e.BTN_MIDDLE,
                e.BTN_TOUCH,
            ]

        capabilities = {
            e.EV_KEY: key_codes,
            e.EV_ABS: [
                (
                    e.ABS_X,
                    evdev.AbsInfo(
                        value=0,
                        min=0,
                        max=ABS_MAX_COORDINATE,
                        fuzz=0,
                        flat=0,
                        resolution=100,
                    ),
                ),
                (
                    e.ABS_Y,
                    evdev.AbsInfo(
                        value=0,
                        min=0,
                        max=ABS_MAX_COORDINATE,
                        fuzz=0,
                        flat=0,
                        resolution=100,
                    ),
                ),
                (
                    e.ABS_PRESSURE,
                    evdev.AbsInfo(
                        value=0,
                        min=0,
                        max=ABS_MAX_PRESSURE,
                        fuzz=0,
                        flat=0,
                        resolution=0,
                    ),
                ),
                (
                    e.ABS_TILT_X,
                    evdev.AbsInfo(
                        value=0,
                        min=TILT_MIN,
                        max=TILT_MAX,
                        fuzz=0,
                        flat=0,
                        resolution=0,
                    ),
                ),
                (
                    e.ABS_TILT_Y,
                    evdev.AbsInfo(
                        value=0,
                        min=TILT_MIN,
                        max=TILT_MAX,
                        fuzz=0,
                        flat=0,
                        resolution=0,
                    ),
                ),
            ],
        }

        input_props = [e.INPUT_PROP_DIRECT] if self.direct_mode else [e.INPUT_PROP_POINTER]

        logger.info(f"Creating device '{self.name}' [mode={self.mode}, direct={self.direct_mode}]")
        self.uinput = evdev.UInput(
            events=capabilities,
            name=self.name,
            version=0x01,
            input_props=input_props,
        )
        logger.info(f"Device created: {self.uinput.device.path}")
        time.sleep(0.3)

    @staticmethod
    def _get_button_code(action: str) -> Optional[int]:
        if action == "right_click":
            return e.BTN_RIGHT
        elif action == "middle_click":
            return e.BTN_MIDDLE
        elif action == "left_click":
            return e.BTN_LEFT
        return None

    def handle_event(self, ev: PenEvent):
        """Process a PenEvent and write corresponding evdev events."""
        if self.uinput is None:
            return

        # Stroke smoothing logic. Only ACTION_MOVE (an actual drawn stroke) is
        # ever smoothed. Every other action - DOWN, UP, CANCEL, and critically
        # HOVER_ENTER/HOVER_MOVE (hovering to position the cursor before
        # touching down) - tracks the raw position directly. Without this,
        # hover events matched none of the branches here, so the smoothed
        # coordinate stayed frozen at wherever it was last set (e.g. the end
        # of the previous stroke) for as long as the pen was only hovering -
        # the cursor would not follow the pen at all while hovering, then
        # suddenly jump to the real position the moment it touched down.
        if self.stroke_smoothing > 0.0 and ev.action == ACTION_MOVE:
            if self._smooth_x is None:
                self._smooth_x, self._smooth_y = ev.x, ev.y
            else:
                alpha = 1.0 - self.stroke_smoothing
                self._smooth_x = alpha * ev.x + (1.0 - alpha) * self._smooth_x
                self._smooth_y = alpha * ev.y + (1.0 - alpha) * self._smooth_y
            coord_x, coord_y = self._smooth_x, self._smooth_y
        else:
            self._smooth_x, self._smooth_y = ev.x, ev.y
            coord_x, coord_y = ev.x, ev.y

        abs_x, abs_y = self._map_coordinates(coord_x, coord_y)
        pressure_val = self.calibrate_pressure(ev.pressure)
        tilt_x = int(max(TILT_MIN, min(TILT_MAX, ev.tilt_x)))
        tilt_y = int(max(TILT_MIN, min(TILT_MAX, ev.tilt_y)))

        is_tablet_mode = (self.mode == "tablet")

        # Barrel Button state
        has_stylus_btn = bool(ev.buttons & BUTTON_STYLUS)
        if has_stylus_btn != self._button_stylus_pressed:
            if is_tablet_mode:
                self.uinput.write(e.EV_KEY, e.BTN_STYLUS, 1 if has_stylus_btn else 0)
            else:
                code = self._get_button_code(self.button_primary)
                if code is not None:
                    self.uinput.write(e.EV_KEY, code, 1 if has_stylus_btn else 0)
            self._button_stylus_pressed = has_stylus_btn

        has_stylus2_btn = bool(ev.buttons & BUTTON_STYLUS2)
        if has_stylus2_btn != self._button_stylus2_pressed:
            if is_tablet_mode:
                self.uinput.write(e.EV_KEY, e.BTN_STYLUS2, 1 if has_stylus2_btn else 0)
            else:
                code = self._get_button_code(self.button_secondary)
                if code is not None:
                    self.uinput.write(e.EV_KEY, code, 1 if has_stylus2_btn else 0)
            self._button_stylus2_pressed = has_stylus2_btn

        # Tablet tool proximity management (ONLY in tablet mode)
        if is_tablet_mode:
            tool_code = e.BTN_TOOL_RUBBER if ev.tool_type == TOOL_ERASER else e.BTN_TOOL_PEN
            if not self._is_in_proximity or self._active_tool != ev.tool_type:
                if self._is_in_proximity and self._active_tool != ev.tool_type:
                    old_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                    self.uinput.write(e.EV_KEY, old_code, 0)
                self.uinput.write(e.EV_KEY, tool_code, 1)
                self._is_in_proximity = True
                self._active_tool = ev.tool_type

        # Action Handling
        if ev.action in (ACTION_HOVER_MOVE, ACTION_HOVER_ENTER):
            if self._is_down:
                self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
                if self.click_on_touch:
                    self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                    if not is_tablet_mode:
                        self.uinput.write(e.EV_KEY, e.BTN_LEFT, 0)
                self._is_down = False

            self.uinput.write(e.EV_ABS, e.ABS_X, abs_x)
            self.uinput.write(e.EV_ABS, e.ABS_Y, abs_y)
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_X, tilt_x)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_Y, tilt_y)

        elif ev.action == ACTION_DOWN:
            self.uinput.write(e.EV_ABS, e.ABS_X, abs_x)
            self.uinput.write(e.EV_ABS, e.ABS_Y, abs_y)
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, max(1, pressure_val))
            self.uinput.write(e.EV_ABS, e.ABS_TILT_X, tilt_x)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_Y, tilt_y)
            if self.click_on_touch:
                self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 1)
                if not is_tablet_mode:
                    self.uinput.write(e.EV_KEY, e.BTN_LEFT, 1)
            self._is_down = True

        elif ev.action == ACTION_MOVE:
            self.uinput.write(e.EV_ABS, e.ABS_X, abs_x)
            self.uinput.write(e.EV_ABS, e.ABS_Y, abs_y)
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, pressure_val)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_X, tilt_x)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_Y, tilt_y)
            if self.click_on_touch:
                if not self._is_down and pressure_val > 0:
                    self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 1)
                    if not is_tablet_mode:
                        self.uinput.write(e.EV_KEY, e.BTN_LEFT, 1)
                    self._is_down = True

        elif ev.action in (ACTION_UP, ACTION_CANCEL):
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
            if self.click_on_touch:
                self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                if not is_tablet_mode:
                    self.uinput.write(e.EV_KEY, e.BTN_LEFT, 0)
            self._is_down = False
            self._smooth_x = None
            self._smooth_y = None

        elif ev.action == ACTION_HOVER_EXIT:
            if self._is_down:
                self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
                if self.click_on_touch:
                    self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                    if not is_tablet_mode:
                        self.uinput.write(e.EV_KEY, e.BTN_LEFT, 0)
                self._is_down = False
            if is_tablet_mode:
                tool_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                self.uinput.write(e.EV_KEY, tool_code, 0)
                self._is_in_proximity = False
            self._smooth_x = None
            self._smooth_y = None

        self.uinput.syn()

        # Invoke live callback for UI monitoring
        if self.on_event_processed:
            try:
                self.on_event_processed(ev, pressure_val, abs_x, abs_y)
            except Exception:
                pass

    def _release_touch(self):
        """Release BTN_TOUCH/BTN_LEFT without touching self._is_down (matches
        the original VirtualTablet.update_settings behavior exactly - the
        caller in TabletBackendBase.update_settings is responsible for that)."""
        if not self.uinput:
            return
        self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
        if self.mode != "tablet":
            self.uinput.write(e.EV_KEY, e.BTN_LEFT, 0)
        self.uinput.syn()

    def close(self):
        """Safely release all buttons and close the uinput device."""
        if self.uinput is not None:
            try:
                if self._is_down:
                    self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                    if self.mode != "tablet":
                        self.uinput.write(e.EV_KEY, e.BTN_LEFT, 0)
                if self.mode == "tablet" and self._is_in_proximity:
                    tool_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                    self.uinput.write(e.EV_KEY, tool_code, 0)
                if self._button_stylus_pressed:
                    btn = e.BTN_STYLUS if self.mode == "tablet" else self._get_button_code(self.button_primary)
                    if btn is not None:
                        self.uinput.write(e.EV_KEY, btn, 0)
                if self._button_stylus2_pressed:
                    btn = e.BTN_STYLUS2 if self.mode == "tablet" else self._get_button_code(self.button_secondary)
                    if btn is not None:
                        self.uinput.write(e.EV_KEY, btn, 0)
                self.uinput.syn()
                self.uinput.close()
            except Exception as err:
                logger.warning(f"Error during uinput cleanup: {err}")
            finally:
                self.uinput = None
                logger.info("Virtual tablet device closed")
