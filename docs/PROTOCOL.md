# S Pen Bridge — Network Wire Protocol (v1)

This document defines the binary wire protocol used for transmitting S Pen events between the Android tablet client and the Linux server over TCP.

All integers and floating-point values are encoded in **Little-Endian** (`<` in Python `struct`).

---

## 1. Packet Header (9 bytes)

Every packet begins with a fixed 9-byte header:

| Offset | Field | Type | Size | Description |
|---|---|---|---|---|
| `0` | `magic` | char[4] | 4 | Magic identifier: ASCII `SPEN` (`0x53 0x50 0x45 0x4E`) |
| `4` | `pkt_type` | uint8 | 1 | Packet type identifier (see table below) |
| `5` | `seq` | uint16 | 2 | Monotonically increasing sequence number |
| `7` | `payload_len` | uint16 | 2 | Length of payload in bytes ($N \times 24$ for events) |

### Packet Types

| Value | Name | Description |
|---|---|---|
| `0x01` | `PKT_EVENT` | Contains one or more Pen Event records |
| `0x02` | `PKT_PING` | Heartbeat probe sent by client or server |
| `0x03` | `PKT_PONG` | Heartbeat response |
| `0x04` | `PKT_HANDSHAKE` | Initial connection handshake and feature negotiation |

---

## 2. Event Record (24 bytes)

When `pkt_type == PKT_EVENT`, the payload contains one or more 24-byte event records:

| Offset | Field | Type | Size | Valid Range | Description |
|---|---|---|---|---|---|
| `0` | `action` | uint8 | 1 | `0..6` | Event action type |
| `1` | `tool_type` | uint8 | 1 | `0..2` | Stylus, Eraser, or Finger |
| `2` | `buttons` | uint16 | 2 | Bitfield | Barrel buttons and touch flags |
| `4` | `x` | float32 | 4 | `0.0 .. 1.0` | Normalized horizontal position |
| `8` | `y` | float32 | 4 | `0.0 .. 1.0` | Normalized vertical position |
| `12` | `pressure` | float32 | 4 | `0.0 .. 1.0` | Pressure sensitivity (4096 hardware levels) |
| `16` | `tilt_x` | float32 | 4 | `-90.0 .. 90.0` | Stylus tilt angle along X axis in degrees |
| `20` | `tilt_y` | float32 | 4 | `-90.0 .. 90.0` | Stylus tilt angle along Y axis in degrees |

### Action Types (`action`)

| Value | Identifier | Android MotionEvent Equivalent | evdev Action |
|---|---|---|---|
| `0` | `ACTION_HOVER_MOVE` | `ACTION_HOVER_MOVE` | Update `ABS_X`, `ABS_Y`, `ABS_TILT` (pressure=0) |
| `1` | `ACTION_HOVER_ENTER` | `ACTION_HOVER_ENTER` | Assert `BTN_TOOL_PEN = 1` |
| `2` | `ACTION_HOVER_EXIT` | `ACTION_HOVER_EXIT` | Assert `BTN_TOOL_PEN = 0` |
| `3` | `ACTION_DOWN` | `ACTION_DOWN` | Assert `BTN_TOUCH = 1`, update coords & pressure |
| `4` | `ACTION_MOVE` | `ACTION_MOVE` | Update `ABS_X`, `ABS_Y`, `ABS_PRESSURE`, tilt |
| `5` | `ACTION_UP` | `ACTION_UP` | Assert `BTN_TOUCH = 0`, pressure = 0 |
| `6` | `ACTION_CANCEL` | `ACTION_CANCEL` | Assert `BTN_TOUCH = 0`, pressure = 0 |

### Tool Types (`tool_type`)

| Value | Identifier | Description |
|---|---|---|
| `0` | `TOOL_STYLUS` | Active S Pen tip |
| `1` | `TOOL_ERASER` | Inverted pen or eraser tool button |
| `2` | `TOOL_FINGER` | Capacitive touch contact |

### Button Bitfield (`buttons`)

| Bit | Hex | Identifier | Description |
|---|---|---|---|
| 0 | `0x0001` | `BUTTON_STYLUS` | Primary S Pen barrel button |
| 1 | `0x0002` | `BUTTON_STYLUS2` | Secondary stylus button |
| 2 | `0x0004` | `BUTTON_TOUCH` | Tip surface contact |

---

## 3. Historical Batching

During rapid drawing strokes, Android batches intermediate sensor reports in `MotionEvent.getHistorySize()`. The client flattens all historical events followed by the final coordinate into a single `PKT_EVENT` payload:

$$\text{payload\_len} = (K_{\text{history}} + 1) \times 24 \text{ bytes}$$

This allows sampling rates up to 240Hz–480Hz with negligible network overhead and zero dropped curves.
