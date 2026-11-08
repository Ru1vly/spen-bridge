"""Find the tablet's LAN address independently of the server's bind address."""

import ipaddress
import json
from pathlib import Path
import subprocess
import sys


def _usable_ipv4(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and not (address.is_loopback or address.is_link_local
                                            or address.is_unspecified or address.is_multicast)
    except ValueError:
        return False


def _linux_addresses():
    result = subprocess.run(["ip", "-j", "-4", "address", "show", "up", "scope", "global"],
                            capture_output=True, text=True, timeout=1.0, check=False)
    if result.returncode != 0:
        return []
    candidates = []
    for interface in json.loads(result.stdout):
        name = interface.get("ifname", "").split("@", 1)[0]
        directory = Path("/sys/class/net") / name
        if not (directory / "device").exists():
            continue  # Exclude VPN, bridge, container and other virtual interfaces.
        wireless = (directory / "wireless").exists() or (directory / "phy80211").exists()
        for entry in interface.get("addr_info", []):
            address = entry.get("local", "")
            if entry.get("family") == "inet" and _usable_ipv4(address):
                candidates.append((0 if wireless else 1, name, address))
    return [item[2] for item in sorted(candidates)]


def _qt_addresses():
    # Native adapter types distinguish Wi-Fi/Ethernet from VPNs on Windows.
    from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
    candidates = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not (flags & QNetworkInterface.InterfaceFlag.IsUp
                and flags & QNetworkInterface.InterfaceFlag.IsRunning):
            continue
        kind = interface.type()
        if kind not in (QNetworkInterface.InterfaceType.Wifi, QNetworkInterface.InterfaceType.Ethernet):
            continue
        if sys.platform.startswith("linux") and not (Path("/sys/class/net") / interface.name() / "device").exists():
            continue
        for entry in interface.addressEntries():
            address = entry.ip()
            if address.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and _usable_ipv4(address.toString()):
                candidates.append((0 if kind == QNetworkInterface.InterfaceType.Wifi else 1,
                                   interface.name(), address.toString()))
    return [item[2] for item in sorted(candidates)]


def get_local_ip() -> str:
    """Prefer a wireless adapter, then physical LAN; never return USB loopback.

    An empty result means there is no usable LAN address. Public-route probes
    are deliberately avoided: a VPN can own that route while Wi-Fi is available.
    """
    if sys.platform.startswith("linux"):
        try:
            addresses = _linux_addresses()
            if addresses:
                return addresses[0]
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
            pass
    try:
        addresses = _qt_addresses()
        return addresses[0] if addresses else ""
    except (ImportError, OSError, RuntimeError, ValueError):
        return ""
