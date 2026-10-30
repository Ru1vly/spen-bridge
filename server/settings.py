"""Resolve one validated configuration into backend options for CLI and GUI."""
from server.monitors import detect_monitors

PROFILE_SETTINGS = (
    "click_on_touch", "pressure_curve_type", "pressure_gamma", "pressure_min",
    "pressure_max", "stroke_smoothing", "button_primary", "button_secondary",
)


def effective_settings(config, detected=None):
    config.validate()
    monitors, desktop = detected if detected is not None else detect_monitors()
    bounds, size = config.get_screen_bounds_and_desktop(monitors, desktop)
    profile = config.get_active_profile()
    return dict(
        name=config.device_name, mode=profile.device_mode, direct_mode=profile.direct_mode,
        screen_bounds=bounds, desktop_size=size,
        aspect_ratio_lock=config.aspect_ratio_lock, tablet_aspect_ratio=config.tablet_aspect_ratio,
        **{key: getattr(profile, key) for key in PROFILE_SETTINGS},
    )


def runtime_settings(settings):
    return {k: v for k, v in settings.items() if k not in ("name", "mode", "direct_mode")}


def listener_address(config):
    """A stored pre-v2 wildcard address alone does not opt into Wi-Fi."""
    return config.host if config.wifi_enabled else "127.0.0.1"
