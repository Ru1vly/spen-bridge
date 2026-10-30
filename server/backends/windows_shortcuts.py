"""Explicit Ctrl+Z action for the Windows profile's Undo button binding."""
import ctypes


def send_undo():
    user = ctypes.WinDLL("user32", use_last_error=True)
    ulong_ptr = ctypes.c_size_t
    word, dword, long = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32

    class Keyboard(ctypes.Structure):
        _fields_ = [("vk", word), ("scan", word), ("flags", dword),
                    ("time", dword), ("extra", ulong_ptr)]

    class Mouse(ctypes.Structure):
        _fields_ = [("x", long), ("y", long), ("data", dword),
                    ("flags", dword), ("time", dword), ("extra", ulong_ptr)]

    class Data(ctypes.Union):
        _fields_ = [("keyboard", Keyboard), ("mouse", Mouse)]

    class Input(ctypes.Structure):
        _fields_ = [("type", dword), ("data", Data)]

    user.SendInput.argtypes = [dword, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = dword
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = ctypes.c_int16

    def key(vk, up=False):
        item = Input()
        item.type = 1
        item.data.keyboard = Keyboard(vk, 0, 2 if up else 0, 0, 0)
        events = (Input * 1)(item)
        if user.SendInput(1, events, ctypes.sizeof(Input)) != 1:
            error = getattr(ctypes, "get_last_error", lambda: 0)()
            raise OSError(error, "Windows refused the Undo shortcut; check the focused application's permissions")

    # Do not release a Ctrl key physically held by the user.
    control_down = bool(user.GetAsyncKeyState(0x11) & 0x8000)
    if user.GetAsyncKeyState(0x5A) & 0x8000:
        return  # Do not release a physically held Z key.
    try:
        if not control_down:
            key(0x11)
        key(0x5A)
    finally:
        try:
            key(0x5A, True)
        finally:
            if not control_down:
                key(0x11, True)
