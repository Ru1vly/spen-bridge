"""Local network helpers for the GUI: LAN IP detection."""

import json
import ipaddress
from pathlib import Path

import socket
import subprocess
import sys


def get_local_ip() -> str:
    """Detect local LAN IP address."""
    if sys.platform.startswith("linux"):
        try:
            result = subprocess.run(["ip", "-j", "-4", "address", "show", "up", "scope", "global"],
                                    capture_output=True, text=True, timeout=1.0, check=False)
            for interface in json.loads(result.stdout):
                name = interface.get("ifname", "").split("@", 1)[0]
                if not (Path("/sys/class/net") / name / "device").exists():
                    continue  # VPN/tunnel/container routes are not the tablet's LAN.
                for address in interface.get("addr_info", []):
                    if address.get("family") == "inet":
                        ip = ipaddress.ip_address(address["local"])
                        if not ip.is_loopback and not ip.is_link_local:
                            return str(ip)
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
            pass
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
