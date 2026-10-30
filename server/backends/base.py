"""
Shared, OS-agnostic pieces of the virtual tablet backend: settings storage,
pressure calibration, and coordinate mapping. Concrete backends (Linux
uinput, Windows HID) subclass TabletBackendBase and implement the
platform-specific device I/O in `_setup_device`, `handle_event`, `close`,
and `_release_touch`.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Tuple

from server.protocol import PenEvent
from server.pressure import pressure_output
from server import validation as validate

_UNSET = object()

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
        self._validate_settings(dict(
            name=name, mode=mode, direct_mode=direct_mode,
            screen_bounds=screen_bounds, desktop_size=desktop_size,
            pressure_curve_type=pressure_curve_type, pressure_gamma=pressure_gamma,
            pressure_min=pressure_min, pressure_max=pressure_max,
            stroke_smoothing=stroke_smoothing, button_primary=button_primary,
            button_secondary=button_secondary, click_on_touch=click_on_touch,
            aspect_ratio_lock=aspect_ratio_lock, tablet_aspect_ratio=tablet_aspect_ratio,
        ))
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

    @staticmethod
    def _validate_settings(values):
        for name, value in values.items():
            if name in ("screen_bounds", "desktop_size"):
                if value is not None:
                    validate.dimensions(value, name, rectangle=name == "screen_bounds")
            elif name in ("click_on_touch", "aspect_ratio_lock", "direct_mode"):
                validate.boolean(value, name)
            elif name == "tablet_aspect_ratio":
                validate.aspect_ratio(value)
            elif name in ("button_primary", "button_secondary"):
                validate.choice(value, name, validate.BUTTON_ACTIONS)
            elif name == "pressure_curve_type":
                validate.choice(value, name, validate.PRESSURE_CURVES)
            elif name in ("pressure_min", "pressure_max", "pressure_gamma", "stroke_smoothing"):
                bounds = {"pressure_min": (0, .5), "pressure_max": (.5, 1),
                          "pressure_gamma": (.1, 5), "stroke_smoothing": (0, .9)}
                validate.number(value, name, *bounds[name])
            elif name == "mode":
                validate.choice(value, name, {"pointer", "tablet"})
            elif name == "name":
                validate.text(value, name)
            else:
                raise ValueError(f"Unknown tablet setting: {name}")

    def update_settings(
        self,
        screen_bounds=_UNSET,
        desktop_size=_UNSET,
        pressure_curve_type=None,
        pressure_gamma=None,
        pressure_min=None,
        pressure_max=None,
        stroke_smoothing=None,
        button_primary=None,
        button_secondary=None,
        click_on_touch=None,
        aspect_ratio_lock=None,
        tablet_aspect_ratio=None,
    ):
        """Validate the complete change before applying it; None clears mapping."""
        values = dict(
            pressure_curve_type=pressure_curve_type, pressure_gamma=pressure_gamma,
            pressure_min=pressure_min, pressure_max=pressure_max,
            stroke_smoothing=stroke_smoothing, button_primary=button_primary,
            button_secondary=button_secondary, click_on_touch=click_on_touch,
            aspect_ratio_lock=aspect_ratio_lock, tablet_aspect_ratio=tablet_aspect_ratio,
        )
        values = {k: v for k, v in values.items() if v is not None}
        if screen_bounds is not _UNSET:
            values["screen_bounds"] = screen_bounds
        if desktop_size is not _UNSET:
            values["desktop_size"] = desktop_size
        self._validate_settings(values)
        if values.get("click_on_touch") is False and self._is_down:
            self._release_touch()
            self._is_down = False
        for name, value in values.items():
            setattr(self, name, value)

    def calibrate_pressure(self, raw_p: float) -> int:
        return int(pressure_output(raw_p, self.pressure_curve_type, self.pressure_gamma,
                                   self.pressure_min, self.pressure_max) * self.PRESSURE_MAX)

    def _map_coordinates(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        Map normalized [0.0, 1.0] coordinates to tablet integer range [0, 65535].
        If screen_bounds and desktop_size are configured, maps to that specific monitor.
        Otherwise maps directly across the full range.
        """
        clamped_x = max(0.0, min(1.0, norm_x))
        clamped_y = max(0.0, min(1.0, norm_y))

        # Preserve physical proportions by fitting a centered target rectangle
        # with the tablet's aspect inside the selected desktop region.
        if self.screen_bounds is not None:
            validate.dimensions(self.screen_bounds, "screen_bounds", rectangle=True)
        if self.desktop_size is not None:
            validate.dimensions(self.desktop_size, "desktop_size")
        if self.screen_bounds is not None and self.desktop_size is None:
            raise ValueError("Region mapping requires desktop dimensions")
        if self.screen_bounds is not None or self.aspect_ratio_lock:
            dw, dh = self.desktop_size or (1920, 1080)
            sx, sy, sw, sh = self.screen_bounds or (0, 0, dw, dh)
            if self.aspect_ratio_lock:
                ratio = validate.aspect_ratio(self.tablet_aspect_ratio)
                fit_w, fit_h = min(sw, sh * ratio), min(sh, sw / ratio)
                sx, sy = sx + (sw - fit_w) / 2, sy + (sh - fit_h) / 2
                sw, sh = fit_w, fit_h
            return (
                max(0, min(self.COORD_MAX, int(((sx + clamped_x * sw) / dw) * self.COORD_MAX))),
                max(0, min(self.COORD_MAX, int(((sy + clamped_y * sh) / dh) * self.COORD_MAX))),
            )
        return int(clamped_x * self.COORD_MAX), int(clamped_y * self.COORD_MAX)

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
