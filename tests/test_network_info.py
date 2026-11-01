"""LAN discovery must not advertise the VPN's public-route address."""
import json
from unittest.mock import Mock, patch

from server.gui.network_info import get_local_ip


def test_lan_address_ignores_vpn_and_virtual_interfaces():
    addresses = [
        {"ifname": "byedpi-tun", "addr_info": [{"family": "inet", "local": "172.20.0.1"}]},
        {"ifname": "tailscale0", "addr_info": [{"family": "inet", "local": "100.77.1.2"}]},
        {"ifname": "wlan0", "addr_info": [{"family": "inet", "local": "192.168.1.15"}]},
    ]
    with patch("server.gui.network_info.sys.platform", "linux"), \
         patch("server.gui.network_info.subprocess.run", return_value=Mock(stdout=json.dumps(addresses))), \
         patch("server.gui.network_info.Path.exists", autospec=True,
               side_effect=lambda p: p.parent.name == "wlan0"), \
         patch("server.gui.network_info.socket.socket") as socket:
        assert get_local_ip() == "192.168.1.15"
        socket.assert_not_called()
