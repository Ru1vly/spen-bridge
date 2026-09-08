"""Local network helpers for the GUI: LAN IP detection."""

import socket
import subprocess
import sys


def get_local_ip() -> str:
    """Detect local LAN IP address."""
    if sys.platform != "win32":
        try:
            res = subprocess.run(
                ["ip", "-4", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            parts = res.stdout.split()
            if "src" in parts:
                idx = parts.index("src")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
