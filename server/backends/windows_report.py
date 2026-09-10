"""Portable HID wire contract; mirrored by windows/driver/spenvhid/ioctl.h."""
import struct

INTERFACE_GUID = "{781EF630-72B2-4EAF-A81D-34B3D635A901}"
IOCTL_SUBMIT_REPORT = (0x22 << 16) | (2 << 14) | (0x800 << 2)
PEN_REPORT = struct.Struct("<BBHHHbb")
MOUSE_REPORT = struct.Struct("<BBbb")
TIP, BARREL, IN_RANGE, INVERT, ERASER = 1, 2, 4, 8, 16


def pack_pen(flags=0, x=0, y=0, pressure=0, tilt_x=0, tilt_y=0):
    """Pack report 1: switches, coordinates, pressure and signed degree tilt."""
    def clamp(value, low, high):
        return max(low, min(high, int(value)))
    return PEN_REPORT.pack(1, flags & 31, clamp(x, 0, 32767),
                           clamp(y, 0, 32767), clamp(pressure, 0, 32767),
                           clamp(tilt_x, -90, 90), clamp(tilt_y, -90, 90))


def pack_mouse(buttons=0):
    """Report 2 supplies remapped mouse buttons without moving the cursor."""
    return MOUSE_REPORT.pack(2, buttons & 7, 0, 0)
