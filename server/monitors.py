"""
Monitor detection and geometry helper.
Detects active screens and computes overall virtual desktop geometry.
Supports PySide6 QScreen, xrandr, and swaymsg.
"""

import json
import logging
import re
import subprocess
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("SPenMonitors")


def get_monitors_from_xrandr() -> List[Dict[str, Any]]:
    """Parse xrandr output to find connected monitors and their geometries."""
    monitors = []
    try:
        res = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode != 0:
            return monitors

        # Example matching: eDP-1 connected primary 1920x1080+0+1080 or HDMI-A-1 connected 1920x1080+0+0
        pattern = re.compile(
            r"^(\S+)\s+connected\s+(primary\s+)?(\d+)x(\d+)\+(\d+)\+(\d+)"
        )
        for line in res.stdout.splitlines():
            m = pattern.match(line)
            if m:
                name = m.group(1)
                is_primary = bool(m.group(2))
                w = int(m.group(3))
                h = int(m.group(4))
                x = int(m.group(5))
                y = int(m.group(6))
                monitors.append({
                    "name": name,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "primary": is_primary,
                })
    except Exception as e:
        logger.debug(f"xrandr query failed: {e}")

    return monitors


def get_monitors_from_sway() -> List[Dict[str, Any]]:
    """Query swaymsg for output geometries if running under Sway / wlroots."""
    monitors = []
    try:
        res = subprocess.run(
            ["swaymsg", "-t", "get_outputs", "--raw"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode == 0:
            outputs = json.loads(res.stdout)
            for out in outputs:
                if out.get("active", True):
                    rect = out.get("rect", {})
                    monitors.append({
                        "name": out.get("name", "Unknown"),
                        "x": rect.get("x", 0),
                        "y": rect.get("y", 0),
                        "width": rect.get("width", 1920),
                        "height": rect.get("height", 1080),
                        "primary": out.get("primary", False),
                    })
    except Exception as e:
        logger.debug(f"swaymsg query failed: {e}")

    return monitors


def get_monitors_from_qt() -> List[Dict[str, Any]]:
    """Query PySide6 QGuiApplication screens."""
    monitors = []
    try:
        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication.instance()
        if app is not None:
            primary = app.primaryScreen()
            for screen in app.screens():
                geom = screen.geometry()
                monitors.append({
                    "name": screen.name(),
                    "x": geom.x(),
                    "y": geom.y(),
                    "width": geom.width(),
                    "height": geom.height(),
                    "primary": (screen == primary),
                })
    except Exception as e:
        logger.debug(f"Qt screen query failed: {e}")

    return monitors


def detect_monitors() -> Tuple[List[Dict[str, Any]], Tuple[int, int]]:
    """
    Detect all active monitors and total desktop bounding size.
    Returns (list_of_monitors, (desktop_width, desktop_height)).
    """
    # Prefer Qt if available and populated, then xrandr, then sway
    monitors = get_monitors_from_qt()
    if not monitors:
        monitors = get_monitors_from_xrandr()
    if not monitors:
        monitors = get_monitors_from_sway()

    if not monitors:
        # Fallback default single screen
        monitors = [{
            "name": "Default Screen",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "primary": True,
        }]

    # Compute bounding box of all monitors
    max_x = max(m["x"] + m["width"] for m in monitors)
    max_y = max(m["y"] + m["height"] for m in monitors)
    min_x = min(m["x"] for m in monitors)
    min_y = min(m["y"] for m in monitors)

    desktop_width = max(1920, max_x - min(0, min_x))
    desktop_height = max(1080, max_y - min(0, min_y))

    return monitors, (desktop_width, desktop_height)
