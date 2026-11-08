"""The visible connection address belongs to Wi-Fi/LAN, not USB or a VPN."""
import json
from unittest.mock import Mock, patch

from server.gui.network_info import get_local_ip


def linux_result(interfaces, physical, wireless):
    def exists(path):
        return path.parent.name in (wireless if path.name in ('wireless', 'phy80211') else physical)
    return (
        patch('server.gui.network_info.sys.platform', 'linux'),
        patch('server.gui.network_info.subprocess.run', return_value=Mock(returncode=0, stdout=json.dumps(interfaces))),
        patch('server.gui.network_info.Path.exists', autospec=True, side_effect=exists),
    )


def test_lan_address_ignores_vpn_and_virtual_interfaces():
    interfaces = [{'ifname': name, 'addr_info': [{'family': 'inet', 'local': address}]} for name, address in
                  [('byedpi-tun', '172.20.0.1'), ('tailscale0', '100.77.1.2'), ('wlan0', '192.168.1.15')]]
    a,b,c=linux_result(interfaces, {'wlan0'}, {'wlan0'})
    with a,b,c,patch('server.gui.network_info._qt_addresses') as fallback:
        assert get_local_ip() == '192.168.1.15'
        fallback.assert_not_called()


def test_wifi_wins_over_usb_and_ethernet_even_when_listed_last():
    interfaces = [{'ifname': name, 'addr_info': [{'family': 'inet', 'local': address}]} for name, address in
                  [('usb0', '192.168.42.1'), ('eth0', '10.0.0.20'), ('wlp0s20f3', '192.168.1.15')]]
    a,b,c=linux_result(interfaces, {'usb0','eth0','wlp0s20f3'}, {'wlp0s20f3'})
    with a,b,c:
        assert get_local_ip() == '192.168.1.15'


def test_no_network_does_not_advertise_loopback_or_default_vpn_route():
    a,b,c=linux_result([], set(), set())
    with a,b,c,patch('server.gui.network_info._qt_addresses',return_value=[]):
        assert get_local_ip() == ''


def test_ethernet_is_a_lan_fallback_when_wifi_is_unavailable():
    a,b,c=linux_result([{'ifname':'eth0','addr_info':[{'family':'inet','local':'10.0.0.20'}]}], {'eth0'}, set())
    with a,b,c:
        assert get_local_ip() == '10.0.0.20'
