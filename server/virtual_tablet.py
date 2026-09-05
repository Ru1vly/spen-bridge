"""
Virtual Drawing Tablet implementation using Linux uinput via python-evdev.
Creates a kernel-level input device that drawing software (Krita, GIMP,
Blender, Inkscape, etc.) recognizes as a professional graphics tablet.
"""

import logging
import time
from typing import Optional, Tuple
import evdev
from evdev import ecodes as e

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

ABS_MAX_COORDINATE = 65535
ABS_MAX_PRESSURE = 4095
TILT_MIN = -90
TILT_MAX = 90


class VirtualTablet:
    """Emulates a Wacom-compatible graphics tablet stylus via /dev/uinput."""

    def __init__(
        self,
        name: str = "Samsung S Pen Virtual Tablet",
        direct_mode: bool = False,
        screen_bounds: Optional[Tuple[int, int, int, int]] = None,
        desktop_size: Optional[Tuple[int, int]] = None,
    ):
        """
        Args:
            name: Device name shown in system / xinput / libinput
            direct_mode: If True, flags INPUT_PROP_DIRECT (screen-mapped Cintiq style)
            screen_bounds: (x_offset, y_offset, width, height) of target monitor in desktop pixels
            desktop_size: (total_width, total_height) of the full virtual desktop in pixels
        """
        self.name = name
        self.direct_mode = direct_mode
        self.screen_bounds = screen_bounds
        self.desktop_size = desktop_size

        self.uinput: Optional[evdev.UInput] = None
        self._is_in_proximity = False
        self._is_down = False
        self._active_tool = TOOL_STYLUS
        self._button_stylus_pressed = False
        self._button_stylus2_pressed = False

        self._setup_device()

    def _setup_device(self):
        """Register device capabilities with the Linux uinput kernel driver."""
        capabilities = {
            e.EV_KEY: [
                e.BTN_TOOL_PEN,
                e.BTN_TOOL_RUBBER,
                e.BTN_TOUCH,
                e.BTN_STYLUS,
                e.BTN_STYLUS2,
            ],
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

        logger.info(f"Creating virtual tablet device: {self.name} (direct={self.direct_mode})")
        self.uinput = evdev.UInput(
            events=capabilities,
            name=self.name,
            version=0x01,
            input_props=input_props,
        )
        logger.info(f"Device created: {self.uinput.device.path}")
        # Allow kernel and display server / libinput to discover and initialize device
        time.sleep(0.3)

    def _map_coordinates(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        Map normalized [0.0, 1.0] coordinates to tablet integer range [0, 65535].
        If screen_bounds and desktop_size are configured, maps to that specific monitor.
        """
        clamped_x = max(0.0, min(1.0, norm_x))
        clamped_y = max(0.0, min(1.0, norm_y))

        if self.screen_bounds and self.desktop_size:
            sx, sy, sw, sh = self.screen_bounds
            dw, dh = self.desktop_size
            pixel_x = sx + clamped_x * sw
            pixel_y = sy + clamped_y * sh
            mapped_x = int((pixel_x / dw) * ABS_MAX_COORDINATE)
            mapped_y = int((pixel_y / dh) * ABS_MAX_COORDINATE)
            return (
                max(0, min(ABS_MAX_COORDINATE, mapped_x)),
                max(0, min(ABS_MAX_COORDINATE, mapped_y)),
            )

        return (
            int(clamped_x * ABS_MAX_COORDINATE),
            int(clamped_y * ABS_MAX_COORDINATE),
        )

    def handle_event(self, ev: PenEvent):
        """Process a PenEvent and write corresponding evdev events."""
        if self.uinput is None:
            return

        tool_code = e.BTN_TOOL_RUBBER if ev.tool_type == TOOL_ERASER else e.BTN_TOOL_PEN
        abs_x, abs_y = self._map_coordinates(ev.x, ev.y)
        pressure_val = int(max(0.0, min(1.0, ev.pressure)) * ABS_MAX_PRESSURE)
        tilt_x = int(max(TILT_MIN, min(TILT_MAX, ev.tilt_x)))
        tilt_y = int(max(TILT_MIN, min(TILT_MAX, ev.tilt_y)))

        # Update Tool Proximity
        if not self._is_in_proximity or self._active_tool != ev.tool_type:
            if self._is_in_proximity and self._active_tool != ev.tool_type:
                # Switch active tool
                old_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                self.uinput.write(e.EV_KEY, old_code, 0)

            self.uinput.write(e.EV_KEY, tool_code, 1)
            self._is_in_proximity = True
            self._active_tool = ev.tool_type

        # Update Stylus Barrel Buttons
        has_stylus_btn = bool(ev.buttons & BUTTON_STYLUS)
        if has_stylus_btn != self._button_stylus_pressed:
            self.uinput.write(e.EV_KEY, e.BTN_STYLUS, 1 if has_stylus_btn else 0)
            self._button_stylus_pressed = has_stylus_btn

        has_stylus2_btn = bool(ev.buttons & BUTTON_STYLUS2)
        if has_stylus2_btn != self._button_stylus2_pressed:
            self.uinput.write(e.EV_KEY, e.BTN_STYLUS2, 1 if has_stylus2_btn else 0)
            self._button_stylus2_pressed = has_stylus2_btn

        # Handle Action States
        if ev.action in (ACTION_HOVER_MOVE, ACTION_HOVER_ENTER):
            if self._is_down:
                self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
                self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
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
            self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 1)
            self._is_down = True

        elif ev.action == ACTION_MOVE:
            self.uinput.write(e.EV_ABS, e.ABS_X, abs_x)
            self.uinput.write(e.EV_ABS, e.ABS_Y, abs_y)
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, pressure_val)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_X, tilt_x)
            self.uinput.write(e.EV_ABS, e.ABS_TILT_Y, tilt_y)
            if not self._is_down and pressure_val > 0:
                self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 1)
                self._is_down = True

        elif ev.action in (ACTION_UP, ACTION_CANCEL):
            self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
            self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
            self._is_down = False

        elif ev.action == ACTION_HOVER_EXIT:
            if self._is_down:
                self.uinput.write(e.EV_ABS, e.ABS_PRESSURE, 0)
                self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                self._is_down = False
            self.uinput.write(e.EV_KEY, tool_code, 0)
            self._is_in_proximity = False

        self.uinput.syn()

    def close(self):
        """Safely release all buttons and close the uinput device."""
        if self.uinput is not None:
            try:
                if self._is_down:
                    self.uinput.write(e.EV_KEY, e.BTN_TOUCH, 0)
                if self._is_in_proximity:
                    tool_code = e.BTN_TOOL_RUBBER if self._active_tool == TOOL_ERASER else e.BTN_TOOL_PEN
                    self.uinput.write(e.EV_KEY, tool_code, 0)
                if self._button_stylus_pressed:
                    self.uinput.write(e.EV_KEY, e.BTN_STYLUS, 0)
                if self._button_stylus2_pressed:
                    self.uinput.write(e.EV_KEY, e.BTN_STYLUS2, 0)
                self.uinput.syn()
                self.uinput.close()
            except Exception as err:
                logger.warning(f"Error during uinput cleanup: {err}")
            finally:
                self.uinput = None
                logger.info("Virtual tablet device closed")
