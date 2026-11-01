"""
Configuration manager for S Pen Bridge.
Supports persistent JSON storage, per-application profiles, and auto-switching.
"""

from dataclasses import dataclass, asdict, field
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from server import validation as validate
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("SPenConfig")

if sys.platform == "win32":
    DEFAULT_CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "spen-bridge"
else:
    DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "spen-bridge"
CONFIG_FILE_PATH = DEFAULT_CONFIG_DIR / "config.json"
_SAVE_LOCK = threading.RLock()


@dataclass
class AppProfile:
    name: str = "Default"
    app_matches: List[str] = field(default_factory=list)  # e.g. ["osu!", "osu", "osu-lazer"]
    click_on_touch: bool = True                           # False for osu!
    device_mode: str = "pointer"                          # "pointer" or "tablet"
    direct_mode: bool = False                             # INPUT_PROP_DIRECT (display tablet mode)
    mapping_mode: str = "all"                             # "all", "monitor", "custom"
    selected_monitor: str = ""
    custom_bounds: List[int] = field(default_factory=lambda: [0, 0, 1920, 1080])
    pressure_curve_type: str = "linear"                   # "linear", "soft", "firm", "sigmoid", "custom"
    pressure_gamma: float = 1.0
    pressure_min: float = 0.0
    pressure_max: float = 1.0
    stroke_smoothing: float = 0.0
    button_primary: str = "right_click"
    button_secondary: str = "middle_click"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppProfile":
        if not isinstance(data, dict):
            raise ValueError("Each profile must be an object")
        valid = set(cls.__dataclass_fields__)
        profile = cls(**{k: v for k, v in data.items() if k in valid})
        profile.validate()
        return profile

    def validate(self):
        validate.text(self.name, "Profile name", limit=80)
        if not isinstance(self.app_matches, list) or len(self.app_matches) > 128:
            raise ValueError("Profile match rules must be a list of at most 128 strings")
        for match in self.app_matches:
            validate.text(match, "Match rule")
        for name in ("click_on_touch", "direct_mode"):
            validate.boolean(getattr(self, name), name)
        validate.choice(self.device_mode, "device mode", {"pointer", "tablet"})
        validate.choice(self.mapping_mode, "mapping mode", {"all", "monitor", "custom"})
        validate.text(self.selected_monitor, "Selected monitor", empty=True)
        validate.dimensions(self.custom_bounds, "Custom bounds", rectangle=True)
        validate.choice(self.pressure_curve_type, "pressure curve", validate.PRESSURE_CURVES)
        for name, low, high in (("pressure_gamma", .1, 5), ("pressure_min", 0, .5),
                                ("pressure_max", .5, 1), ("stroke_smoothing", 0, .9)):
            validate.number(getattr(self, name), name, low, high)
        if self.pressure_min >= self.pressure_max:
            raise ValueError("Pressure minimum must be smaller than maximum")
        for name in ("button_primary", "button_secondary"):
            validate.choice(getattr(self, name), name, validate.BUTTON_ACTIONS)


def get_builtin_default_profiles() -> Dict[str, AppProfile]:
    """Neutral fallback only; application profiles are created by the user."""
    return {"Default": AppProfile(name="Default")}



@dataclass
class TabletConfig:
    # Server network settings
    host: str = "127.0.0.1"
    port: int = 40118
    wifi_enabled: bool = False
    auto_start_server: bool = True
    auto_adb_forward: bool = False
    minimize_to_tray: bool = True

    # Virtual tablet device settings
    device_name: str = "Samsung S Pen Virtual Tablet"
    desktop_size: List[int] = field(default_factory=lambda: [1920, 1080])
    aspect_ratio_lock: bool = False
    tablet_aspect_ratio: str = "16:10"

    # Per-App Profiles & Auto-switching
    auto_switch_profiles: bool = False
    active_profile_name: str = "Default"
    profiles: Dict[str, AppProfile] = field(default_factory=get_builtin_default_profiles)
    recovery_notice: str = field(default="", init=False, repr=False)

    def validate(self):
        validate.bind_address(self.host)
        validate.number(self.port, "Server port", 1024, 65535, integer=True)
        for name in ("auto_start_server", "auto_adb_forward", "minimize_to_tray",
                     "aspect_ratio_lock", "auto_switch_profiles", "wifi_enabled"):
            validate.boolean(getattr(self, name), name)
        validate.text(self.device_name, "Device name")
        validate.dimensions(self.desktop_size, "Desktop dimensions")
        validate.aspect_ratio(self.tablet_aspect_ratio)
        if not isinstance(self.profiles, dict) or not 1 <= len(self.profiles) <= 256:
            raise ValueError("Configuration must contain 1..256 profiles")
        if "Default" not in self.profiles or self.active_profile_name not in self.profiles:
            raise ValueError("Default and active profiles must exist")
        for key, profile in self.profiles.items():
            if not isinstance(profile, AppProfile) or profile.name != key:
                raise ValueError("Profile name must match its dictionary key")
            profile.validate()

    def get_active_profile(self) -> AppProfile:
        if self.active_profile_name in self.profiles:
            return self.profiles[self.active_profile_name]
        if "Default" in self.profiles:
            return self.profiles["Default"]
        default_p = AppProfile(name="Default")
        self.profiles["Default"] = default_p
        return default_p

    def find_profile_for_app(self, app_id: str, title: str) -> Optional[AppProfile]:
        """Match active window against configured profiles."""
        if not app_id and not title:
            return None

        app_id_lower = app_id.lower()
        title_lower = title.lower()

        # Prioritize specific app profiles over Default
        for prof_name, prof in self.profiles.items():
            if prof_name == "Default":
                continue
            for match in prof.app_matches:
                m = match.strip().lower()
                if not m:
                    continue
                if m in app_id_lower or m in title_lower:
                    return prof

        return self.profiles.get("Default")

    # Property proxies to active profile for 100% backward compatibility
    @property
    def click_on_touch(self) -> bool:
        return self.get_active_profile().click_on_touch

    @click_on_touch.setter
    def click_on_touch(self, val: bool):
        self.get_active_profile().click_on_touch = val

    @property
    def device_mode(self) -> str:
        return self.get_active_profile().device_mode

    @device_mode.setter
    def device_mode(self, val: str):
        self.get_active_profile().device_mode = val

    @property
    def direct_mode(self) -> bool:
        return self.get_active_profile().direct_mode

    @direct_mode.setter
    def direct_mode(self, val: bool):
        self.get_active_profile().direct_mode = val

    @property
    def mapping_mode(self) -> str:
        return self.get_active_profile().mapping_mode

    @mapping_mode.setter
    def mapping_mode(self, val: str):
        self.get_active_profile().mapping_mode = val

    @property
    def selected_monitor(self) -> str:
        return self.get_active_profile().selected_monitor

    @selected_monitor.setter
    def selected_monitor(self, val: str):
        self.get_active_profile().selected_monitor = val

    @property
    def custom_bounds(self) -> List[int]:
        return self.get_active_profile().custom_bounds

    @custom_bounds.setter
    def custom_bounds(self, val: List[int]):
        self.get_active_profile().custom_bounds = val

    @property
    def pressure_curve_type(self) -> str:
        return self.get_active_profile().pressure_curve_type

    @pressure_curve_type.setter
    def pressure_curve_type(self, val: str):
        self.get_active_profile().pressure_curve_type = val

    @property
    def pressure_gamma(self) -> float:
        return self.get_active_profile().pressure_gamma

    @pressure_gamma.setter
    def pressure_gamma(self, val: float):
        self.get_active_profile().pressure_gamma = val

    @property
    def pressure_min(self) -> float:
        return self.get_active_profile().pressure_min

    @pressure_min.setter
    def pressure_min(self, val: float):
        self.get_active_profile().pressure_min = val

    @property
    def pressure_max(self) -> float:
        return self.get_active_profile().pressure_max

    @pressure_max.setter
    def pressure_max(self, val: float):
        self.get_active_profile().pressure_max = val

    @property
    def stroke_smoothing(self) -> float:
        return self.get_active_profile().stroke_smoothing

    @stroke_smoothing.setter
    def stroke_smoothing(self, val: float):
        self.get_active_profile().stroke_smoothing = val

    @property
    def button_primary(self) -> str:
        return self.get_active_profile().button_primary

    @button_primary.setter
    def button_primary(self, val: str):
        self.get_active_profile().button_primary = val

    @property
    def button_secondary(self) -> str:
        return self.get_active_profile().button_secondary

    @button_secondary.setter
    def button_secondary(self, val: str):
        self.get_active_profile().button_secondary = val

    def get_screen_bounds_and_desktop(
        self,
        detected_monitors: Optional[list] = None,
        detected_desktop_size: Optional[Tuple[int, int]] = None,
    ) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int]]]:
        """Compute effective (screen_bounds, desktop_size) tuple for active profile.

        `detected_desktop_size`, when given, is a freshly-detected (width, height)
        bounding box (e.g. from monitors.detect_monitors()) and always takes
        priority over the persisted self.desktop_size. Without this, "monitor"/
        "custom" mapping used the config's last-saved desktop_size as the
        denominator for scaling to the uinput ABS coordinate range regardless of
        whether it still matched reality: a stale or default value there
        (e.g. a taller multi-monitor desktop_size against a single 1080p
        monitor) silently caps how far down/right the pen can ever reach.
        """
        prof = self.get_active_profile()
        if detected_desktop_size and len(detected_desktop_size) >= 2:
            desk_w, desk_h = detected_desktop_size[0], detected_desktop_size[1]
        else:
            desk_w = self.desktop_size[0] if len(self.desktop_size) >= 2 else 1920
            desk_h = self.desktop_size[1] if len(self.desktop_size) >= 2 else 1080
        effective_desk = (desk_w, desk_h)
        validate.dimensions(effective_desk, "Desktop dimensions")
        if prof.mapping_mode == "all":
            return None, effective_desk if self.aspect_ratio_lock else None

        if prof.mapping_mode == "custom" and len(prof.custom_bounds) == 4:
            sb = (prof.custom_bounds[0], prof.custom_bounds[1], prof.custom_bounds[2], prof.custom_bounds[3])
            return sb, effective_desk

        if prof.mapping_mode == "monitor" and detected_monitors:
            for mon in detected_monitors:
                if mon.get("name") == prof.selected_monitor:
                    sb = (mon["x"], mon["y"], mon["width"], mon["height"])
                    return sb, effective_desk

        return None, None

    def to_dict(self) -> dict:
        prof = self.get_active_profile()
        d = {
            "host": self.host,
            "wifi_enabled": self.wifi_enabled,
            "port": self.port,
            "auto_start_server": self.auto_start_server,
            "auto_adb_forward": self.auto_adb_forward,
            "minimize_to_tray": self.minimize_to_tray,
            "device_name": self.device_name,
            "desktop_size": self.desktop_size,
            "aspect_ratio_lock": self.aspect_ratio_lock,
            "tablet_aspect_ratio": self.tablet_aspect_ratio,
            "auto_switch_profiles": self.auto_switch_profiles,
            "active_profile_name": self.active_profile_name,
            "profiles": {k: v.to_dict() for k, v in self.profiles.items()},
            # Active profile mirrors for backward compatibility
            "click_on_touch": prof.click_on_touch,
            "device_mode": prof.device_mode,
            "direct_mode": prof.direct_mode,
            "mapping_mode": prof.mapping_mode,
            "selected_monitor": prof.selected_monitor,
            "custom_bounds": prof.custom_bounds,
            "pressure_curve_type": prof.pressure_curve_type,
            "pressure_gamma": prof.pressure_gamma,
            "pressure_min": prof.pressure_min,
            "pressure_max": prof.pressure_max,
            "stroke_smoothing": prof.stroke_smoothing,
            "button_primary": prof.button_primary,
            "button_secondary": prof.button_secondary,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TabletConfig":
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        cfg = cls()
        cfg.host = data.get("host", cfg.host)
        cfg.wifi_enabled = data.get("wifi_enabled", False)
        cfg.port = data.get("port", cfg.port)
        cfg.auto_start_server = data.get("auto_start_server", cfg.auto_start_server)
        cfg.auto_adb_forward = data.get("auto_adb_forward", cfg.auto_adb_forward)
        cfg.minimize_to_tray = data.get("minimize_to_tray", cfg.minimize_to_tray)
        cfg.device_name = data.get("device_name", cfg.device_name)
        cfg.desktop_size = data.get("desktop_size", cfg.desktop_size)
        cfg.aspect_ratio_lock = data.get("aspect_ratio_lock", cfg.aspect_ratio_lock)
        cfg.tablet_aspect_ratio = data.get("tablet_aspect_ratio", cfg.tablet_aspect_ratio)
        cfg.auto_switch_profiles = data.get("auto_switch_profiles", cfg.auto_switch_profiles)
        cfg.active_profile_name = data.get("active_profile_name", cfg.active_profile_name)

        # Parse profiles
        profiles_raw = data.get("profiles")
        if profiles_raw is not None and not isinstance(profiles_raw, dict):
            raise ValueError("Profiles must be an object")
        if isinstance(profiles_raw, dict):
            cfg.profiles = {}
            for name, raw in profiles_raw.items():
                if not isinstance(raw, dict):
                    raise ValueError("Each profile must be an object")
                # The dictionary key is the canonical name in legacy files.
                cfg.profiles[name] = AppProfile.from_dict(dict(raw, name=name))
            cfg.profiles.setdefault("Default", AppProfile())
            if cfg.active_profile_name not in cfg.profiles:
                cfg.active_profile_name = "Default"
            # Migrate the old global "direct_mode" flag into any profile whose own
            # serialized data didn't already carry a per-profile value.
            legacy_direct_mode = data.get("direct_mode", False)
            for prof_name, raw_prof in profiles_raw.items():
                if prof_name in cfg.profiles and "direct_mode" not in raw_prof:
                    cfg.profiles[prof_name].direct_mode = legacy_direct_mode
        else:
            # Migration from legacy flat config
            defaults = get_builtin_default_profiles()
            if "Default" in defaults:
                def_p = defaults["Default"]
                def_p.click_on_touch = data.get("click_on_touch", True)
                def_p.device_mode = data.get("device_mode", "pointer")
                def_p.direct_mode = data.get("direct_mode", False)
                def_p.mapping_mode = data.get("mapping_mode", "all")
                def_p.selected_monitor = data.get("selected_monitor", "")
                def_p.custom_bounds = data.get("custom_bounds", [0, 0, 1920, 1080])
                def_p.pressure_curve_type = data.get("pressure_curve_type", "linear")
                def_p.pressure_gamma = data.get("pressure_gamma", 1.0)
                def_p.pressure_min = data.get("pressure_min", 0.0)
                def_p.pressure_max = data.get("pressure_max", 1.0)
                def_p.stroke_smoothing = data.get("stroke_smoothing", 0.0)
                def_p.button_primary = data.get("button_primary", "right_click")
                def_p.button_secondary = data.get("button_secondary", "middle_click")
            cfg.profiles = defaults

        cfg.validate()
        return cfg


def _read_config(path):
    with path.open("r", encoding="utf-8") as stream:
        return TabletConfig.from_dict(json.load(stream))


def load_config() -> TabletConfig:
    """Recover a validated last-good backup without replacing damaged evidence."""
    if not CONFIG_FILE_PATH.exists():
        return TabletConfig()
    try:
        return _read_config(CONFIG_FILE_PATH)
    except (ValueError, TypeError, OSError) as error:
        logger.warning("Cannot load configuration: %s", error)
        notice = "Settings could not be read. Built-in defaults are active."
        try:
            recovered = _read_config(CONFIG_FILE_PATH.with_suffix(".json.bak"))
            notice = "Settings were damaged. The last valid backup is active; save to restore it."
        except (ValueError, TypeError, OSError):
            recovered = TabletConfig()
        try:
            damaged = CONFIG_FILE_PATH.with_name(f"config.json.corrupt-{time.time_ns()}")
            _atomic_write(damaged, CONFIG_FILE_PATH.read_bytes())
        except OSError:
            logger.warning("Could not preserve the damaged configuration", exc_info=True)
        recovered.recovery_notice = notice
        return recovered


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if sys.platform != "win32":
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_config(config: TabletConfig) -> bool:
    """Validate first, preserve the last good version, then atomically replace."""
    with _SAVE_LOCK:
        try:
            config.validate()
            content = (json.dumps(config.to_dict(), indent=2, allow_nan=False) + "\n").encode("utf-8")
            if CONFIG_FILE_PATH.exists():
                try:
                    previous = _read_config(CONFIG_FILE_PATH)
                except (ValueError, TypeError, OSError):
                    previous = None
                if previous is not None:
                    backup = (json.dumps(previous.to_dict(), indent=2, allow_nan=False) + "\n").encode("utf-8")
                    _atomic_write(CONFIG_FILE_PATH.with_suffix(".json.bak"), backup)
            _atomic_write(CONFIG_FILE_PATH, content)
            config.recovery_notice = ""
            logger.info("Saved configuration to %s", CONFIG_FILE_PATH)
            return True
        except (ValueError, TypeError, OSError) as error:
            logger.error("Cannot save configuration: %s", error)
            return False
