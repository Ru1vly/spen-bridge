"""Parse read-only ADB transport facts; never restart or reconfigure a server."""

import re


def parse_transport_metadata(status, host_features, route_features=None):
    def field(name):
        match = re.search(r"^" + name + r":\s*(.+)$", status, re.MULTILINE)
        return match[1].strip().strip('"') if match else None

    def features(text):
        if not text or not re.fullmatch(r"[a-z0-9_]+(?:,[a-z0-9_]+)*", text.strip()):
            return None
        return set(text.strip().split(","))

    host = features(host_features)
    route = features(route_features)
    burst = field("burst_mode")
    return dict(
        adb_version=field("version"),
        usb_backend=field("usb_backend"),
        server_burst_mode_enabled={"true": True, "false": False}.get(burst),
        host_advertises_delayed_ack=None if host is None else "delayed_ack" in host,
        route_advertises_delayed_ack=None if route is None else "delayed_ack" in route,
        device_support_without_host_gate="unknown: route features may be limited by the host configuration",
        mutation_performed=False,
    )
