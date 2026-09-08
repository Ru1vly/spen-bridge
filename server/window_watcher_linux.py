"""
Active window detection helper for Linux desktop compositors.
Supports driftwm, sway, hyprland, and X11/xprop.
"""

import json
import logging
import os
import subprocess
from typing import Tuple

logger = logging.getLogger("SPenWindowWatcher")


def get_active_window() -> Tuple[str, str]:
    """
    Detect currently focused window application ID and title.
    Returns (app_id, window_title).
    """
    # 1. Check driftwm state file
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    drift_state = os.path.join(runtime_dir, "driftwm", "state")
    if os.path.isfile(drift_state):
        try:
            with open(drift_state, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("windows="):
                        wins = json.loads(line[8:])
                        for w in wins:
                            if w.get("is_focused"):
                                return str(w.get("app_id", "")), str(w.get("title", ""))
        except Exception:
            pass

    # 2. Check swaymsg
    if os.environ.get("SWAYSOCK"):
        try:
            res = subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=0.4)
            if res.returncode == 0:
                def _find_focused(node):
                    if node.get("focused"):
                        app = node.get("app_id") or node.get("window_properties", {}).get("class", "")
                        return app, node.get("name", "")
                    for child in node.get("nodes", []) + node.get("floating_nodes", []):
                        r = _find_focused(child)
                        if r:
                            return r
                    return None
                tree = json.loads(res.stdout)
                focused = _find_focused(tree)
                if focused:
                    return str(focused[0] or ""), str(focused[1] or "")
        except Exception:
            pass

    # 3. Check hyprctl
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            res = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=0.4)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return str(data.get("class", "")), str(data.get("title", ""))
        except Exception:
            pass

    # 4. Check xprop (X11 / Xwayland)
    if os.environ.get("DISPLAY"):
        try:
            res = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=0.4)
            if res.returncode == 0 and "window id #" in res.stdout:
                win_id = res.stdout.split()[-1]
                if win_id and win_id != "0x0":
                    res2 = subprocess.run(["xprop", "-id", win_id, "WM_CLASS", "_NET_WM_NAME"], capture_output=True, text=True, timeout=0.4)
                    app_id = ""
                    title = ""
                    for line in res2.stdout.splitlines():
                        if "WM_CLASS" in line:
                            # e.g. WM_CLASS(STRING) = "osu!", "osu!"
                            parts = line.split("=", 1)
                            if len(parts) > 1:
                                app_id = parts[1].replace('"', '').strip()
                        elif "_NET_WM_NAME" in line:
                            parts = line.split("=", 1)
                            if len(parts) > 1:
                                title = parts[1].replace('"', '').strip()
                    if app_id or title:
                        return app_id, title
        except Exception:
            pass

    return "", ""
