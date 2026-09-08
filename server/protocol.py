"""
S Pen Bridge: Network Protocol Definition.

Binary packet specification:
- Header (9 bytes):
    magic:       4 bytes (b"SPEN")
    pkt_type:    1 byte  (uint8)
    seq:         2 bytes (uint16, little-endian)
    payload_len: 2 bytes (uint16, little-endian)

- Event Record (24 bytes):
    action:      1 byte  (uint8)
    tool_type:   1 byte  (uint8)
    buttons:     2 bytes (uint16, little-endian)
    x:           4 bytes (float32, 0.0 - 1.0)
    y:           4 bytes (float32, 0.0 - 1.0)
    pressure:    4 bytes (float32, 0.0 - 1.0)
    tilt_x:      4 bytes (float32, degrees -90.0 to 90.0)
    tilt_y:      4 bytes (float32, degrees -90.0 to 90.0)
"""

import struct
from dataclasses import dataclass
from typing import List, Tuple, Optional

MAGIC = b"SPEN"
HEADER_STRUCT = struct.Struct("<4sBHH")
HEADER_SIZE = HEADER_STRUCT.size  # 9 bytes

EVENT_STRUCT = struct.Struct("<BBHfffff")
EVENT_RECORD_SIZE = EVENT_STRUCT.size  # 24 bytes

# Packet Types
PKT_EVENT = 1
PKT_PING = 2
PKT_PONG = 3
PKT_HANDSHAKE = 4

# Action Types (matching Android MotionEvent semantics)
ACTION_HOVER_MOVE = 0
ACTION_HOVER_ENTER = 1
ACTION_HOVER_EXIT = 2
ACTION_DOWN = 3
ACTION_MOVE = 4
ACTION_UP = 5
ACTION_CANCEL = 6

# Tool Types
TOOL_STYLUS = 0
TOOL_ERASER = 1
TOOL_FINGER = 2

# Button bitflags
BUTTON_STYLUS = 1 << 0   # Barrel button
BUTTON_STYLUS2 = 1 << 1  # Second barrel button (if present)
BUTTON_TOUCH = 1 << 2    # Tip contact


@dataclass(slots=True)
class PenEvent:
    action: int
    tool_type: int
    buttons: int
    x: float
    y: float
    pressure: float
    tilt_x: float = 0.0
    tilt_y: float = 0.0


def pack_packet(pkt_type: int, seq: int, payload: bytes) -> bytes:
    """Pack a full packet with header and payload."""
    header = HEADER_STRUCT.pack(MAGIC, pkt_type, seq, len(payload))
    return header + payload


def pack_events(events: List[PenEvent], seq: int = 0) -> bytes:
    """Pack a list of PenEvent objects into a PKT_EVENT packet."""
    payload = bytearray()
    for ev in events:
        # Clamp values
        x = max(0.0, min(1.0, float(ev.x)))
        y = max(0.0, min(1.0, float(ev.y)))
        pressure = max(0.0, min(1.0, float(ev.pressure)))
        tilt_x = max(-90.0, min(90.0, float(ev.tilt_x)))
        tilt_y = max(-90.0, min(90.0, float(ev.tilt_y)))
        payload.extend(
            EVENT_STRUCT.pack(
                ev.action,
                ev.tool_type,
                ev.buttons,
                x,
                y,
                pressure,
                tilt_x,
                tilt_y
            )
        )
    return pack_packet(PKT_EVENT, seq, bytes(payload))


def unpack_header(data: bytes, offset: int = 0) -> Optional[Tuple[int, int, int]]:
    """
    Unpack header from a byte buffer at `offset` (must have at least
    HEADER_SIZE bytes remaining from there). Reads directly off `data` via
    unpack_from instead of requiring a pre-sliced copy, so a caller draining
    a growing bytearray can pass it (and an advancing offset) directly.
    Returns (pkt_type, seq, payload_len) or None if invalid magic.
    """
    if len(data) - offset < HEADER_SIZE:
        return None
    magic, pkt_type, seq, payload_len = HEADER_STRUCT.unpack_from(data, offset)
    if magic != MAGIC:
        return None
    return pkt_type, seq, payload_len


def unpack_events(payload: bytes) -> List[PenEvent]:
    """Unpack event records from payload bytes.

    Uses struct.iter_unpack (a C-level iterator, faster than a manual
    unpack_from loop) which requires the buffer length to be an exact
    multiple of the record size - unlike a manual loop, it raises on a
    short trailing fragment instead of silently stopping. Truncating to a
    whole number of records first preserves the previous lenient behavior
    against a malformed/truncated payload_len.
    """
    whole_len = (len(payload) // EVENT_RECORD_SIZE) * EVENT_RECORD_SIZE
    return [
        PenEvent(
            action=action,
            tool_type=tool_type,
            buttons=buttons,
            x=x,
            y=y,
            pressure=pressure,
            tilt_x=tilt_x,
            tilt_y=tilt_y,
        )
        for action, tool_type, buttons, x, y, pressure, tilt_x, tilt_y
        in EVENT_STRUCT.iter_unpack(payload[:whole_len])
    ]
