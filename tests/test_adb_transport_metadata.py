"""Small parser-only tests; no ADB subprocess or attached device."""

import unittest

from audit.adb_transport_metadata import parse_transport_metadata


class AdbTransportMetadataTests(unittest.TestCase):
    def test_disabled_host_does_not_claim_device_unsupported(self):
        result = parse_transport_metadata(
            'version: "37.0.1"\nusb_backend: NATIVE\nburst_mode: false\n',
            "shell_v2,stat_v2",
            "shell_v2",
        )
        self.assertFalse(result["server_burst_mode_enabled"])
        self.assertFalse(result["host_advertises_delayed_ack"])
        self.assertIn("unknown", result["device_support_without_host_gate"])
        self.assertEqual(result["usb_backend"], "NATIVE")
        self.assertFalse(result["mutation_performed"])

    def test_enabled_host_and_route_are_distinct_observations(self):
        result = parse_transport_metadata(
            "burst_mode: true\n", "shell_v2,delayed_ack", "shell_v2,delayed_ack"
        )
        self.assertTrue(result["server_burst_mode_enabled"])
        self.assertTrue(result["host_advertises_delayed_ack"])
        self.assertTrue(result["route_advertises_delayed_ack"])

    def test_unavailable_status_or_phone_remains_unknown(self):
        result = parse_transport_metadata("", "shell_v2")
        self.assertIsNone(result["server_burst_mode_enabled"])
        self.assertIsNone(result["route_advertises_delayed_ack"])
        self.assertIsNone(result["adb_version"])

    def test_error_output_is_not_a_feature_list(self):
        result = parse_transport_metadata("unknown command", "adb: unknown service", "")
        self.assertIsNone(result["host_advertises_delayed_ack"])
        self.assertIsNone(result["route_advertises_delayed_ack"])
