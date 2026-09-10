"""
Tests for the OS backend dispatch (server.backends.factory), using
monkeypatched platform.system() so both branches are exercised regardless of
which OS actually runs the test - neither branch should ever require real
evdev or real ctypes/WinDLL calls just to prove the dispatch itself works.
"""

import platform
import sys
import unittest
from unittest.mock import patch

from server.backends.factory import create_tablet_backend


class TestBackendFactory(unittest.TestCase):
    def test_linux_dispatches_to_uinput_backend(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend = Mock()
        module = SimpleNamespace(LinuxUinputTablet=backend)
        with patch.object(platform, "system", return_value="Linux"), patch.dict(
                sys.modules, {"server.backends.linux_uinput": module}):
            self.assertIs(create_tablet_backend(mode="tablet"), backend.return_value)
            backend.assert_called_once_with(mode="tablet")

    def test_windows_dispatches_without_loading_evdev(self):
        with patch.object(platform, "system", return_value="Windows"), patch(
                "server.backends.windows_hid.DriverConnection"):
            from server.backends.windows_hid import WindowsHidTablet
            tablet = create_tablet_backend()
            self.assertIsInstance(tablet, WindowsHidTablet)
            tablet.close()

    def test_unsupported_platform_raises_runtime_error(self):
        with patch.object(platform, "system", return_value="Plan9"):
            with self.assertRaises(RuntimeError):
                create_tablet_backend()


if __name__ == "__main__":
    unittest.main()
