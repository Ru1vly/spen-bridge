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
import threading
from dataclasses import replace
from typing import Optional

import evdev
from evdev import ecodes as e

from server.button_actions import validate_actions
from server.backends.base import (
    ABS_MAX_COORDINATE,
    ABS_MAX_PRESSURE,
    TILT_MIN,
    TILT_MAX,
    TabletBackendBase,
)
from server.protocol import (
    PenEvent,
    valid_event,
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
        validate_actions("linux", kwargs.get("mode", "pointer"),
                         kwargs.get("button_primary", "right_click"), kwargs.get("button_secondary", "middle_click"))
        self._lock = threading.RLock()
        self._shortcut_device = None
        self._held_codes = set()
        self._eraser_latched = False
        self._last_event = PenEvent(ACTION_CANCEL, TOOL_STYLUS, 0, 0, 0, 0)
        self._last_position = (0, 0)
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

        # Register every supported output up front. Tablet mode still includes
        # BTN_TOOL_PEN, preserving tablet classification; pointer mode omits it.
        key_codes = sorted(set(key_codes + [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE,
                                           e.BTN_STYLUS, e.BTN_STYLUS2]))
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
        # UInput.device is None when evdev cannot open the new event node
        # (e.g. udev has not applied permissions yet); the device still works.
        logger.info(f"Device created: {getattr(self.uinput, 'devnode', None) or 'unknown node'}")
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

    def update_settings(self, **kwargs):
        with self._lock:
            self._validate_settings(kwargs)
            validate_actions("linux", self.mode, kwargs.get("button_primary", self.button_primary),
                             kwargs.get("button_secondary", self.button_secondary))
            if any(key in kwargs and kwargs[key] != getattr(self, key)
                   for key in ("button_primary", "button_secondary", "click_on_touch")):
                self.reset()
            super().update_settings(**kwargs)

    def _button_code(self, action):
        if action == "stylus":
            return e.BTN_STYLUS
        if action == "stylus2":
            return e.BTN_STYLUS2
        if self.mode == "tablet":
            # Native tablet bindings: primary/secondary switches conventionally
            # implement context menu/pan; left click is a shared tip source.
            return {"right_click": e.BTN_STYLUS, "middle_click": e.BTN_STYLUS2,
                    "left_click": e.BTN_TOUCH}.get(action)
        return self._get_button_code(action)

    def _undo(self):
        if self._shortcut_device is None:
            self._shortcut_device = evdev.UInput(
                {e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_Z]}, name=f"{self.name} Shortcuts")
        try:
            for code in (e.KEY_LEFTCTRL, e.KEY_Z):
                self._shortcut_device.write(e.EV_KEY, code, 1)
            self._shortcut_device.syn()
        finally:
            for code in (e.KEY_Z, e.KEY_LEFTCTRL):
                self._shortcut_device.write(e.EV_KEY, code, 0)
            self._shortcut_device.syn()

    def _write_buttons(self, desired):
        for code in sorted(self._held_codes - desired):
            self.uinput.write(e.EV_KEY, code, 0)
        for code in sorted(desired - self._held_codes):
            self.uinput.write(e.EV_KEY, code, 1)
        self._held_codes = desired

    def handle_event(self, ev: PenEvent):
        with self._lock:
            if self.uinput is None or not valid_event(ev):
                return
            if ev.action in (ACTION_CANCEL, ACTION_HOVER_EXIT):
                self.reset(event=ev)
                return
            self._last_event = ev
            if self.stroke_smoothing > 0 and ev.action == ACTION_MOVE and self._smooth_x is not None:
                alpha = 1 - self.stroke_smoothing
                self._smooth_x += alpha * (ev.x - self._smooth_x)
                self._smooth_y += alpha * (ev.y - self._smooth_y)
            else:
                self._smooth_x, self._smooth_y = ev.x, ev.y
            abs_x, abs_y = self._map_coordinates(self._smooth_x, self._smooth_y)
            self._last_position = abs_x, abs_y
            desired = set()
            for mask, action, old_pressed in (
                (BUTTON_STYLUS, self.button_primary, self._button_stylus_pressed),
                (BUTTON_STYLUS2, self.button_secondary, self._button_stylus2_pressed),
            ):
                pressed = bool(ev.buttons & mask)
                if pressed and not old_pressed:
                    if action == "eraser":
                        self._eraser_latched = not self._eraser_latched
                    elif action == "undo":
                        self._undo()
                if pressed:
                    code = self._button_code(action)
                    if code is not None:
                        desired.add(code)
            self._button_stylus_pressed = bool(ev.buttons & BUTTON_STYLUS)
            self._button_stylus2_pressed = bool(ev.buttons & BUTTON_STYLUS2)
            self._is_down = ev.action in (ACTION_DOWN, ACTION_MOVE)
            if self._is_down and self.click_on_touch:
                desired.add(e.BTN_TOUCH)
                if self.mode != "tablet":
                    desired.add(e.BTN_LEFT)
            # Position precedes the contact edge in each synchronized frame.
            self.uinput.write(e.EV_ABS, e.ABS_X, abs_x)
            self.uinput.write(e.EV_ABS, e.ABS_Y, abs_y)
            effective_tool = TOOL_ERASER if ev.tool_type == TOOL_ERASER or self._eraser_latched else TOOL_STYLUS
            if self.mode == "tablet":
                if self._is_in_proximity and self._active_tool != effective_tool:
                    old_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                    self.uinput.write(e.EV_KEY, old_code, 0)
                if not self._is_in_proximity or self._active_tool != effective_tool:
                    self.uinput.write(e.EV_KEY, e.BTN_TOOL_RUBBER if effective_tool == TOOL_ERASER else e.BTN_TOOL_PEN, 1)
                self._active_tool = effective_tool
                self._is_in_proximity = True
            pressure = self.calibrate_pressure(ev.pressure) if self._is_down else 0
            if e.BTN_TOUCH in desired:
                pressure = max(1, pressure)
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, pressure)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_X, int(ev.tilt_x))
            self.uinput.write(e.EV_ABS, e.ABS_TILT_Y, int(ev.tilt_y))
            self._write_buttons(desired)
            self.uinput.syn()
            if ev.action == ACTION_UP:
                self._smooth_x = self._smooth_y = None
            self._notify(replace(ev, tool_type=effective_tool), pressure)

    def _notify(self, event, pressure):
        if self.on_event_processed:
            try:
                self.on_event_processed(event, pressure, *self._last_position)
            except Exception:
                logger.debug("Pen monitoring callback failed", exc_info=True)

    def _release_touch(self):
        with self._lock:
            if self.uinput is not None:
                self._write_buttons(self._held_codes - {e.BTN_TOUCH, e.BTN_LEFT})
                self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
                self.uinput.syn()
            self._is_down = False

    def reset(self, event=None):
        """Release every output regardless of current mappings or wire flags."""
        with self._lock:
            if self.uinput is not None:
                self._write_buttons(set())
                for code in (e.BTN_TOOL_PEN, e.BTN_TOOL_RUBBER) if self.mode == "tablet" else ():
                    self.uinput.write(e.EV_KEY, code, 0)
                for code in (e.ABS_PRESSURE, e.ABS_TILT_X, e.ABS_TILT_Y):
                    self.uinput.write(e.EV_ABS, code, 0)
                self.uinput.syn()
            self._held_codes.clear()
            self._is_down = self._is_in_proximity = False
            self._button_stylus_pressed = self._button_stylus2_pressed = False
            self._eraser_latched = False
            self._smooth_x = self._smooth_y = None
            neutral = replace(event or self._last_event, action=ACTION_CANCEL, buttons=0, pressure=0)
            self._last_event = neutral
            self._notify(neutral, 0)

    def close(self):
        with self._lock:
            if self.uinput is None:
                return
            device = self.uinput
            try:
                self.reset()
            except OSError:
                logger.warning("Unable to release Linux input device", exc_info=True)
            finally:
                self.uinput = None
                try:
                    device.close()
                finally:
                    if self._shortcut_device is not None:
                        self._shortcut_device.close()
                        self._shortcut_device = None
