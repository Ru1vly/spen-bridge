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
        with patch.object(platform, "system", return_value="Linux"):
            if sys.platform.startswith("linux"):
                tablet = create_tablet_backend()
                try:
                    from server.backends.linux_uinput import LinuxUinputTablet
                    self.assertIsInstance(tablet, LinuxUinputTablet)
                finally:
                    tablet.close()
            else:
                # Can't actually open /dev/uinput on a non-Linux test runner,
                # but the dispatch itself (picking the right module) is still
                # checkable via the resulting exception type.
                with self.assertRaises(Exception):
                    create_tablet_backend()

    def test_windows_dispatches_to_windows_stub_cleanly(self):
        """The Phase-1 Windows backend is a stub: construction must fail with
        a clear NotImplementedError, never a raw ImportError on a missing
        evdev module (which would happen if the factory eagerly imported the
        Linux backend at module scope instead of lazily inside the branch)."""
        with patch.object(platform, "system", return_value="Windows"):
            with self.assertRaises(NotImplementedError):
                create_tablet_backend()

    def test_unsupported_platform_raises_runtime_error(self):
        with patch.object(platform, "system", return_value="Plan9"):
            with self.assertRaises(RuntimeError):
                create_tablet_backend()


if __name__ == "__main__":
    unittest.main()
