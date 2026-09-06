"""
Configuration manager for S Pen on Linux.
Supports persistent JSON storage, per-application profiles, and auto-switching.
"""

from dataclasses import dataclass, asdict, field
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

logger = logging.getLogger("SPenConfig")

DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "spenonlinux"
CONFIG_FILE_PATH = DEFAULT_CONFIG_DIR / "config.json"


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
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


def get_builtin_default_profiles() -> Dict[str, AppProfile]:
    """Pre-configured profile presets."""
    return {
        "Default": AppProfile(
            name="Default",
            app_matches=[],
            click_on_touch=True,
            device_mode="pointer",
            mapping_mode="all",
            pressure_curve_type="linear",
            pressure_gamma=1.0,
            pressure_min=0.0,
            pressure_max=1.0,
            stroke_smoothing=0.0,
            button_primary="right_click",
            button_secondary="middle_click",
        ),
        "osu!": AppProfile(
            name="osu!",
            app_matches=["osu!", "osu", "osu-lazer", "osu!.exe"],
            click_on_touch=False,           # Disable click on touch for rhythm tapping with keyboard
            device_mode="pointer",
            mapping_mode="all",
            pressure_curve_type="linear",
            pressure_gamma=1.0,
            pressure_min=0.0,
            pressure_max=1.0,
            stroke_smoothing=0.0,           # Zero latency raw aiming
            button_primary="none",          # Disable barrel button to prevent accidental clicks
            button_secondary="none",
        ),
        "Krita": AppProfile(
            name="Krita",
            app_matches=["krita"],
            click_on_touch=True,
            device_mode="pointer",
            mapping_mode="all",
            pressure_curve_type="soft",     # Soft pressure for natural drawing
            pressure_gamma=0.65,
            pressure_min=0.0,
            pressure_max=1.0,
            stroke_smoothing=0.15,
            button_primary="right_click",   # Krita pop-up palette
            button_secondary="middle_click",
        ),
        "Blender": AppProfile(
            name="Blender",
            app_matches=["blender"],
            click_on_touch=True,
            device_mode="pointer",
            mapping_mode="all",
            pressure_curve_type="linear",
            pressure_gamma=1.0,
            pressure_min=0.0,
            pressure_max=1.0,
            stroke_smoothing=0.0,
            button_primary="middle_click",  # Viewport orbit in Blender
            button_secondary="right_click",
        ),
    }


@dataclass
class TabletConfig:
    # Server network settings
    host: str = "0.0.0.0"
    port: int = 40118
    auto_start_server: bool = True
    auto_adb_forward: bool = False
    minimize_to_tray: bool = False

    # Virtual tablet device settings
    device_name: str = "Samsung S Pen Virtual Tablet"
    desktop_size: List[int] = field(default_factory=lambda: [1920, 1080])
    aspect_ratio_lock: bool = False
    tablet_aspect_ratio: str = "16:10"

    # Per-App Profiles & Auto-switching
    auto_switch_profiles: bool = True
    active_profile_name: str = "Default"
    profiles: Dict[str, AppProfile] = field(default_factory=get_builtin_default_profiles)

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
        whether it still matched reality — a stale or default value there
        (e.g. a taller multi-monitor desktop_size against a single 1080p
        monitor) silently caps how far down/right the pen can ever reach.
        """
        prof = self.get_active_profile()
        if prof.mapping_mode == "all":
            return None, None

        if detected_desktop_size and len(detected_desktop_size) >= 2:
            desk_w, desk_h = detected_desktop_size[0], detected_desktop_size[1]
        else:
            desk_w = self.desktop_size[0] if len(self.desktop_size) >= 2 else 1920
            desk_h = self.desktop_size[1] if len(self.desktop_size) >= 2 else 1080
        effective_desk = (desk_w, desk_h)

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
        cfg = cls()
        cfg.host = data.get("host", cfg.host)
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
        if isinstance(profiles_raw, dict):
            cfg.profiles = {k: AppProfile.from_dict(v) for k, v in profiles_raw.items()}
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

        return cfg


def load_config() -> TabletConfig:
    """Load settings from JSON file or return default configuration."""
    if CONFIG_FILE_PATH.is_file():
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded configuration from {CONFIG_FILE_PATH}")
                return TabletConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load configuration from {CONFIG_FILE_PATH}: {e}. Using defaults.")

    repo_config = Path(__file__).resolve().parent / "config.json"
    if repo_config.is_file():
        try:
            with open(repo_config, "r", encoding="utf-8") as f:
                data = json.load(f)
                return TabletConfig.from_dict(data)
        except Exception:
            pass

    return TabletConfig()


def save_config(config: TabletConfig) -> bool:
    """Save configuration to JSON file."""
    try:
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
        logger.info(f"Saved configuration to {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error saving configuration to {CONFIG_FILE_PATH}: {e}")
        try:
            repo_config = Path(__file__).resolve().parent / "config.json"
            with open(repo_config, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
            return True
        except Exception as e2:
            logger.error(f"Error saving fallback configuration: {e2}")
            return False
