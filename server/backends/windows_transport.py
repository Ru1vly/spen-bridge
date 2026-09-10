"""Synchronous, exclusive connection to the installed SPen VHF source driver."""
import ctypes
from ctypes import wintypes as w
import sys
import uuid

from server.backends.windows_report import INTERFACE_GUID, IOCTL_SUBMIT_REPORT


class DriverConnection:
    def __init__(self):
        self.handle = None
        if sys.platform != "win32":
            raise OSError("The Windows HID driver is only available on Windows.")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        cm = ctypes.WinDLL("cfgmgr32", use_last_error=True)
        self.kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID,
                                            w.DWORD, w.DWORD, w.HANDLE]
        self.kernel.CreateFileW.restype = w.HANDLE
        self.kernel.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD,
                                                w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
        self.kernel.DeviceIoControl.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        cm.CM_Get_Device_Interface_List_SizeW.argtypes = [ctypes.POINTER(w.ULONG), w.LPVOID, w.LPCWSTR, w.ULONG]
        cm.CM_Get_Device_Interface_List_SizeW.restype = w.ULONG
        cm.CM_Get_Device_Interface_ListW.argtypes = [w.LPVOID, w.LPCWSTR, w.LPWSTR, w.ULONG, w.ULONG]
        cm.CM_Get_Device_Interface_ListW.restype = w.ULONG
        guid = ctypes.create_string_buffer(uuid.UUID(INTERFACE_GUID).bytes_le)
        # Retry a device-list change between sizing and reading (CR_BUFFER_SMALL).
        for _ in range(3):
            size = w.ULONG()
            status = cm.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), guid, None, 0)
            if status:
                raise OSError(f"Cannot enumerate S Pen driver (CONFIGRET {status:#x}).")
            paths = ctypes.create_unicode_buffer(max(1, size.value))
            status = cm.CM_Get_Device_Interface_ListW(guid, None, paths, len(paths), 0)
            if status != 0x1A:
                break
        if status:
            raise OSError(f"Cannot enumerate S Pen driver (CONFIGRET {status:#x}).")
        if not paths.value:
            raise OSError("S Pen virtual HID driver not found. Follow docs/WINDOWS.md to install it.")
        handle = self.kernel.CreateFileW(paths.value, 0x40000000, 0, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            raise OSError(error, "Cannot open S Pen driver. Close other bridge instances and check driver permissions. "
                          + ctypes.FormatError(error))
        self.handle = handle

    def submit(self, report):
        if self.handle is None:
            raise OSError("S Pen driver connection is closed.")
        data = ctypes.create_string_buffer(report)
        returned = w.DWORD()
        if not self.kernel.DeviceIoControl(self.handle, IOCTL_SUBMIT_REPORT, data, len(report),
                                           None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
