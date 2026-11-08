# S Pen Bridge: Network Wire Protocol (v2)

This document defines the binary wire protocol used to transmit S Pen events between the Android tablet client and the desktop server (Linux and Windows) over TCP.

All integers and floating-point values are encoded in **little-endian** (`<` in Python `struct`).

## Transport, pairing and ownership

Every connection uses TLS 1.2 or newer. The desktop's per-user identity is stored
in `identity.json` next to its configuration, with an owner-only private key and
256-bit pairing code. The client must pin the SHA-256 fingerprint of the desktop
certificate's DER bytes. Credentials are provisioned by the approved enrollment
flow below, or transferred out of band using advanced manual pairing. Never
accept credentials from an unverified discovery response. The desktop binds
loopback for USB by default; Wi-Fi requires explicit opt-in.

Protocol v1 plaintext connections are rejected. Pairing uses the existing packet
header and packet type 4, before any event may be sent:

1. Desktop sends sequence 0 with payload `SPB2 || nonce`, with a fresh 32-byte
   cryptographically random nonce for each TLS connection.
2. Client responds with sequence 0 and payload `SPB2 || HMAC-SHA256(code,
   "SPB2client\0" || nonce)`. `code` is the ASCII pairing-code string, not its
   Base64-decoded bytes. The displayed code is 43 URL-safe Base64 characters.
3. Desktop acknowledges with sequence 0 and payload `SPB2 || HMAC-SHA256(code,
   "SPB2server\0" || nonce)`. Both sides compare proofs in constant time.

Only one authenticated connection owns the tablet. Other clients cannot inject
events or reset its input state. Disconnect, cancel, idle timeout and server stop
release the owner's state. A new session must not replay an earlier session's
queued strokes. Pairing challenge/proof frames are exactly 36 bytes.

The desktop admits at most four raw/TLS/application connections, with separate
five-second TLS and authentication
deadline and ten-second complete-frame idle deadline. Send an empty PING at least
every two seconds, including while the pen is idle, and verify the matching PONG.
The entire header and payload must arrive within the frame deadline; slow bytes
do not reset it. Default token-bucket budgets are 10,000 events, 4,000 packets and
1 MiB per second, with two-second burst capacity. Limit violations close the
connection and release input. Shutdown closes accepted streams before waiting
for the listener and joins all admitted handlers, including incomplete TLS handshakes.

USB readiness checks use the same pinned TLS connection and fresh mutual proofs,
but the client handshake and server acknowledgement use sequence **1** instead
of 0. The server closes this read-only probe after its acknowledgement. It never
claims input ownership, accepts event packets, resets the current owner or emits
client-connected/disconnected callbacks. This allows a Wi-Fi owner to verify the
paired USB path before an idle handover; older servers can reject the optional
probe without disturbing the Wi-Fi session.

Events must contain complete 24-byte records, at most 2,730 per packet. Unknown
actions/tools/button bits, nonfinite numbers and values outside the ranges below
are rejected before applying any record from that packet. Larger local batches
must be split into complete packets. PING and PONG payloads are empty. Repeated
authentication frames, unknown packet types and invalid magic terminate a session.

Both backends interpret an explicitly enabled finger as one pen/pointer stream,
without multi-touch gestures. The Android app rejects fingers by default. Native
tablet/eraser actions are offered only in device modes that can implement them.

The server preserves all validated samples, including pressure and tilt extrema;
it does not discard already received positions to conceal queue backlog.

## First-time enrollment and discovery

Enrollment uses packet type **5**, with a JSON object payload of at most 2048
UTF-8 bytes. It never claims pen ownership. Existing type-4 session authentication
and the pen event format are unchanged.

Enrollment is available only after **Pair tablet** opens a 120-second window.
At most five attempts and one pending request are accepted per window. After the
normal TLS connection and `SPB2` challenge, the client sends sequence 0
`{stage:"request",name,commitment}`. Both sides create ephemeral P-256 ECDH keys
and 32-byte random nonces. Commitments are SHA-256 of
`"SPEN-PAIR-1\0" || role || "\0" || publicDER || nonce`, with role `client` or
`server`. Byte fields use hexadecimal JSON strings.

The desktop responds with sequence 0 `{stage:"server_commit",name,commitment}`.
The client reveals sequence 1 `{stage:"client_reveal",public_key,nonce}`; the
desktop validates its commitment, then reveals sequence 1
`{stage:"server_reveal",public_key,nonce}`. Both sides validate P-256 keys and reject
reflected keys. Each computes HMAC-SHA256 using the ECDH shared secret over
`"SPEN-PAIR-1\0" || actualTLSCertificateFingerprintBytes || clientPublicDER ||
clientNonce || serverPublicDER || serverNonce`. The first four digest bytes as a
big-endian integer modulo 1,000,000 form the zero-padded six-digit number.
Commitments prevent choosing a new key after seeing the other side's reveal.

The user must compare both numbers and approve on the desktop within 60 seconds
(or the remaining pairing window). Only then does sequence 2
`{stage:"result",approved:true,name,fingerprint,pairing_code,host,port}` transfer
credentials over that TLS connection. Android verifies the returned fingerprint
against the actual TLS certificate before saving. A mismatch, decline, timeout,
backgrounded phone, disconnect or desktop cancellation aborts enrollment. A
successful enrollment closes the window. Subsequent sessions require the stored
certificate pin and normal mutual HMAC proofs. This is an application-specific
numeric-comparison flow, not a Bluetooth implementation or formal security certification.

Discovery is IPv4 UDP broadcast to port **40119**. Queries are JSON
`{service:"spen-bridge",version:1,probe:<16 random bytes in hex>}` (maximum 256
bytes). Only during the explicit pairing window does the desktop reply with the
same service, version and probe plus `name` and TCP `port`. Replies are throttled
per source address and contain no credentials. Android uses the reply source IP,
checks the probe, searches for ten seconds and lists at most 16 desktops.
Discovery identifies candidates; only the number comparison and approval establish
trust. UDP carries discovery only, not pen input.

## Table of Contents

- [1. Packet Header](#1-packet-header-9-bytes)
- [2. Event Record](#2-event-record-24-bytes)
- [3. Historical Batching](#3-historical-batching)

## 1. Packet Header (9 bytes)

Every packet begins with a fixed 9-byte header:

| Offset | Field | Type | Size | Description |
| --- | --- | --- | --- | --- |
| `0` | `magic` | char[4] | 4 | Magic identifier: ASCII `SPEN` (`0x53 0x50 0x45 0x4E`) |
| `4` | `pkt_type` | uint8 | 1 | Packet type identifier (see table below) |
| `5` | `seq` | uint16 | 2 | Client sequence counter, wrapping modulo 65,536 |
| `7` | `payload_len` | uint16 | 2 | Length of payload in bytes (`N x 24` for events) |

### Packet Types

| Value | Name | Description |
| --- | --- | --- |
| `0x01` | `PKT_EVENT` | Contains one or more pen event records |
| `0x02` | `PKT_PING` | Heartbeat probe sent by client or server |
| `0x03` | `PKT_PONG` | Heartbeat response |
| `0x04` | `PKT_HANDSHAKE` | Protocol-v2 challenge and mutual pairing proofs |

## 2. Event Record (24 bytes)

When `pkt_type == PKT_EVENT`, the payload contains one or more 24-byte event records:

| Offset | Field | Type | Size | Valid Range | Description |
| --- | --- | --- | --- | --- | --- |
| `0` | `action` | uint8 | 1 | `0..6` | Event action type |
| `1` | `tool_type` | uint8 | 1 | `0..2` | Stylus, eraser, or finger |
| `2` | `buttons` | uint16 | 2 | Bitfield | Barrel buttons and touch flags |
| `4` | `x` | float32 | 4 | `0.0 .. 1.0` | Normalized horizontal position |
| `8` | `y` | float32 | 4 | `0.0 .. 1.0` | Normalized vertical position |
| `12` | `pressure` | float32 | 4 | `0.0 .. 1.0` | Pressure sensitivity (4096 hardware levels) |
| `16` | `tilt_x` | float32 | 4 | `-90.0 .. 90.0` | Stylus tilt angle along the X axis, in degrees |
| `20` | `tilt_y` | float32 | 4 | `-90.0 .. 90.0` | Stylus tilt angle along the Y axis, in degrees |

### Action Types (`action`)

| Value | Identifier | Android MotionEvent Equivalent | evdev Action |
| --- | --- | --- | --- |
| `0` | `ACTION_HOVER_MOVE` | `ACTION_HOVER_MOVE` | Update `ABS_X`, `ABS_Y`, `ABS_TILT` (pressure = 0) |
| `1` | `ACTION_HOVER_ENTER` | `ACTION_HOVER_ENTER` | Assert `BTN_TOOL_PEN = 1` |
| `2` | `ACTION_HOVER_EXIT` | `ACTION_HOVER_EXIT` | Assert `BTN_TOOL_PEN = 0` |
| `3` | `ACTION_DOWN` | `ACTION_DOWN` | Assert `BTN_TOUCH = 1`, update coordinates and pressure |
| `4` | `ACTION_MOVE` | `ACTION_MOVE` | Update `ABS_X`, `ABS_Y`, `ABS_PRESSURE`, tilt |
| `5` | `ACTION_UP` | `ACTION_UP` | Assert `BTN_TOUCH = 0`, pressure = 0 |
| `6` | `ACTION_CANCEL` | `ACTION_CANCEL` | Assert `BTN_TOUCH = 0`, pressure = 0 |

### Tool Types (`tool_type`)

| Value | Identifier | Description |
| --- | --- | --- |
| `0` | `TOOL_STYLUS` | Active S Pen tip |
| `1` | `TOOL_ERASER` | Inverted pen or eraser tool button |
| `2` | `TOOL_FINGER` | Capacitive touch contact |

### Button Bitfield (`buttons`)

| Bit | Hex | Identifier | Description |
| --- | --- | --- | --- |
| 0 | `0x0001` | `BUTTON_STYLUS` | Primary S Pen barrel button |
| 1 | `0x0002` | `BUTTON_STYLUS2` | Secondary stylus button |
| 2 | `0x0004` | `BUTTON_TOUCH` | Tip surface contact |

## 3. Historical Batching

During rapid drawing strokes, Android batches intermediate sensor reports in `MotionEvent.getHistorySize()`. The client flattens all historical events, followed by the final coordinate, into a single `PKT_EVENT` payload:

$$\text{payload\_len} = (K_{\text{history}} + 1) \times 24 \text{ bytes}$$

The bridge preserves historical samples supplied by Android. Actual sampling rate depends on the digitizer and device load. Session queues must remain bounded; a stalled or disconnected session is reset rather than replaying offline strokes.
