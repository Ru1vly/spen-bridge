"""Windows shortcut ABI and failure cleanup using fake user32, never SendInput."""
import ctypes
import unittest
from unittest.mock import Mock, patch

from server.backends.windows_shortcuts import send_undo


class ShortcutTests(unittest.TestCase):
    def invoke(self, *, held=(), fail_at=None):
        calls = []
        user = Mock()
        user.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk in held else 0

        def send(count, events, size):
            self.assertEqual(count, 1)
            self.assertEqual(size, 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            key = events[0].data.keyboard
            calls.append((key.vk, key.flags))
            return 0 if len(calls) == fail_at else 1

        user.SendInput.side_effect = send
        with patch("ctypes.WinDLL", return_value=user, create=True):
            if fail_at:
                with self.assertRaises(OSError):
                    send_undo()
            else:
                send_undo()
        return calls

    def test_shortcut_has_correct_abi_and_releases_both_keys(self):
        self.assertEqual(self.invoke(), [(0x11, 0), (0x5A, 0), (0x5A, 2), (0x11, 2)])

    def test_physical_modifier_is_not_released(self):
        self.assertEqual(self.invoke(held=(0x11,)), [(0x5A, 0), (0x5A, 2)])
        self.assertEqual(self.invoke(held=(0x5A,)), [])

    def test_partial_failure_still_attempts_release(self):
        self.assertEqual(self.invoke(fail_at=2)[-2:], [(0x5A, 2), (0x11, 2)])
