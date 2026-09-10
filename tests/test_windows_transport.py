"""Exercise discovery, pointer-sized handles and I/O failure paths with Win32 fakes."""
import ctypes
import unittest
from unittest.mock import Mock, patch

from server.backends.windows_transport import DriverConnection
from server.backends.windows_report import pack_pen, IOCTL_SUBMIT_REPORT


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.kernel, self.cm = Mock(), Mock()
        self.path = r'\\?\spenvhid#test'
        def size(out, *args):
            out._obj.value = len(self.path) + 2
            return 0
        def paths(guid, device, out, length, flags):
            out.value = self.path
            return 0
        self.cm.CM_Get_Device_Interface_List_SizeW.side_effect = size
        self.cm.CM_Get_Device_Interface_ListW.side_effect = paths
        self.kernel.CreateFileW.return_value = 0x123456789
        self.kernel.DeviceIoControl.return_value = True
        self.patches = [patch('server.backends.windows_transport.sys.platform', 'win32'),
                        patch.object(ctypes, 'WinDLL', side_effect=[self.kernel, self.cm], create=True)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_discovery_submit_close_preserves_64_bit_handle(self):
        connection = DriverConnection()
        self.assertIs(self.kernel.CreateFileW.restype, ctypes.wintypes.HANDLE)
        self.assertEqual(connection.handle, 0x123456789)
        self.kernel.CreateFileW.assert_called_once_with(self.path, 0x40000000, 0, None, 3, 0, None)
        connection.submit(pack_pen())
        args = self.kernel.DeviceIoControl.call_args.args
        self.assertEqual(args[:2], (0x123456789, IOCTL_SUBMIT_REPORT))
        self.assertEqual(args[3], 10)
        connection.close()
        connection.close()
        self.kernel.CloseHandle.assert_called_once_with(0x123456789)
        with self.assertRaises(OSError):
            connection.submit(pack_pen())

    def test_missing_driver_has_install_guidance(self):
        self.path = ''
        with self.assertRaisesRegex(OSError, 'docs/WINDOWS.md'):
            DriverConnection()
        self.kernel.CreateFileW.assert_not_called()

    def test_list_change_retries(self):
        original = self.cm.CM_Get_Device_Interface_ListW.side_effect
        calls = []
        def changing(*args):
            calls.append(1)
            return 0x1A if len(calls) == 1 else original(*args)
        self.cm.CM_Get_Device_Interface_ListW.side_effect = changing
        connection = DriverConnection()
        self.assertEqual(len(calls), 2)
        connection.close()

    def test_open_failure(self):
        self.kernel.CreateFileW.return_value = ctypes.c_void_p(-1).value
        with patch.object(ctypes, 'get_last_error', return_value=32, create=True), \
             patch.object(ctypes, 'FormatError', return_value='sharing violation', create=True):
            with self.assertRaisesRegex(OSError, 'other bridge instances'):
                DriverConnection()

    def test_ioctl_failure_is_not_silently_dropped(self):
        connection = DriverConnection()
        self.kernel.DeviceIoControl.return_value = False
        with patch.object(ctypes, 'get_last_error', return_value=1167, create=True), \
             patch.object(ctypes, 'WinError', return_value=OSError('disconnected'), create=True):
            with self.assertRaisesRegex(OSError, 'disconnected'):
                connection.submit(pack_pen())
        connection.close()
