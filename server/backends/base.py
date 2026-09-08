"""
Shared, OS-agnostic pieces of the virtual tablet backend: settings storage,
pressure calibration, and coordinate mapping. Concrete backends (Linux
uinput, Windows HID) subclass TabletBackendBase and implement the
platform-specific device I/O in `_setup_device`, `handle_event`, `close`,
and `_release_touch`.
"""

from abc import ABC, abstractmethod
import math
from typing import Callable, Optional, Tuple

from server.protocol import PenEvent

ABS_MAX_COORDINATE = 65535
ABS_MAX_PRESSURE = 4095
TILT_MIN = -90
TILT_MAX = 90


class TabletBackendBase(ABC):
    """Common settings storage + pure math shared by every OS backend."""

    # Coordinate/pressure ceiling for calibrate_pressure()/_map_coordinates()'s
    # output range. Linux keeps the historical uinput ABS_MAX_* defaults;
    # other backends override these class attributes to target their own
    # device's logical range (e.g. Windows HID's 0..32767).
    COORD_MAX = ABS_MAX_COORDINATE
    PRESSURE_MAX = ABS_MAX_PRESSURE

    def __init__(
        self,
        name: str = "Samsung S Pen Virtual Tablet",
        mode: str = "pointer",
        direct_mode: bool = False,
        screen_bounds: Optional[Tuple[int, int, int, int]] = None,
        desktop_size: Optional[Tuple[int, int]] = None,
        pressure_curve_type: str = "linear",
        pressure_gamma: float = 1.0,
        pressure_min: float = 0.0,
        pressure_max: float = 1.0,
        stroke_smoothing: float = 0.0,
        button_primary: str = "right_click",
        button_secondary: str = "middle_click",
        click_on_touch: bool = True,
        aspect_ratio_lock: bool = False,
        tablet_aspect_ratio: str = "16:10",
        on_event_processed: Optional[Callable] = None,
    ):
        self.name = name
        self.mode = mode
        self.direct_mode = direct_mode
        self.screen_bounds = screen_bounds
        self.desktop_size = desktop_size

        # Pressure settings
        self.pressure_curve_type = pressure_curve_type
        self.pressure_gamma = pressure_gamma
        self.pressure_min = max(0.0, min(0.5, pressure_min))
        self.pressure_max = max(0.5, min(1.0, pressure_max))

        # Smoothing & actions
        self.stroke_smoothing = max(0.0, min(0.9, stroke_smoothing))
        self.button_primary = button_primary
        self.button_secondary = button_secondary
        self.click_on_touch = click_on_touch

        self.aspect_ratio_lock = aspect_ratio_lock
        self.tablet_aspect_ratio = tablet_aspect_ratio

        # Live callback
        self.on_event_processed = on_event_processed

        # Shared internal state
        self._is_down = False

        self._setup_device()

    def update_settings(
        self,
        screen_bounds: Optional[Tuple[int, int, int, int]] = None,
        desktop_size: Optional[Tuple[int, int]] = None,
        pressure_curve_type: Optional[str] = None,
        pressure_gamma: Optional[float] = None,
        pressure_min: Optional[float] = None,
        pressure_max: Optional[float] = None,
        stroke_smoothing: Optional[float] = None,
        button_primary: Optional[str] = None,
        button_secondary: Optional[str] = None,
        click_on_touch: Optional[bool] = None,
        **kwargs,
    ):
        """Update runtime settings without re-creating the device."""
        if screen_bounds is not None:
            self.screen_bounds = screen_bounds
        if desktop_size is not None:
            self.desktop_size = desktop_size
        if pressure_curve_type is not None:
            self.pressure_curve_type = pressure_curve_type
        if pressure_gamma is not None:
            self.pressure_gamma = pressure_gamma
        if pressure_min is not None:
            self.pressure_min = max(0.0, min(0.5, pressure_min))
        if pressure_max is not None:
            self.pressure_max = max(0.5, min(1.0, pressure_max))
        if stroke_smoothing is not None:
            self.stroke_smoothing = max(0.0, min(0.9, stroke_smoothing))
        if button_primary is not None:
            self.button_primary = button_primary
        if button_secondary is not None:
            self.button_secondary = button_secondary
        if click_on_touch is not None:
            if not click_on_touch and self._is_down:
                self._release_touch()
            self.click_on_touch = click_on_touch

    def calibrate_pressure(self, raw_p: float) -> int:
        """Apply deadzone, ceiling, and calibrated response curve to raw pressure."""
        if raw_p <= self.pressure_min:
            return 0
        if raw_p >= self.pressure_max:
            norm = 1.0
        else:
            denom = max(0.001, self.pressure_max - self.pressure_min)
            norm = (raw_p - self.pressure_min) / denom

        norm = max(0.0, min(1.0, norm))

        if self.pressure_curve_type == "soft":
            curved = math.pow(norm, 0.65)
        elif self.pressure_curve_type == "firm":
            curved = math.pow(norm, 1.6)
        elif self.pressure_curve_type == "sigmoid":
            curved = norm * norm * (3.0 - 2.0 * norm)
        elif self.pressure_curve_type == "custom":
            gamma = max(0.1, min(5.0, self.pressure_gamma))
            curved = math.pow(norm, gamma)
        else:
            curved = norm

        return int(max(0.0, min(1.0, curved)) * self.PRESSURE_MAX)

    def _map_coordinates(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        Map normalized [0.0, 1.0] coordinates to tablet integer range [0, 65535].
        If screen_bounds and desktop_size are configured, maps to that specific monitor.
        Otherwise maps directly across the full range.
        """
        clamped_x = max(0.0, min(1.0, norm_x))
        clamped_y = max(0.0, min(1.0, norm_y))

        if self.screen_bounds and self.desktop_size:
            sx, sy, sw, sh = self.screen_bounds
            dw, dh = self.desktop_size
            pixel_x = sx + clamped_x * sw
            pixel_y = sy + clamped_y * sh
            mapped_x = int((pixel_x / dw) * self.COORD_MAX)
            mapped_y = int((pixel_y / dh) * self.COORD_MAX)
            return (
                max(0, min(self.COORD_MAX, mapped_x)),
                max(0, min(self.COORD_MAX, mapped_y)),
            )

        return (
            int(clamped_x * self.COORD_MAX),
            int(clamped_y * self.COORD_MAX),
        )

    @abstractmethod
    def _setup_device(self):
        """Register the virtual device with the OS. Called once from __init__."""
        raise NotImplementedError

    @abstractmethod
    def handle_event(self, ev: PenEvent):
        """Process a PenEvent and write corresponding device events."""
        raise NotImplementedError

    @abstractmethod
    def _release_touch(self):
        """Release touch/left-click state on the device (used by update_settings
        when click_on_touch is disabled while the pen is currently down)."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Safely release all buttons and close the device."""
        raise NotImplementedError
