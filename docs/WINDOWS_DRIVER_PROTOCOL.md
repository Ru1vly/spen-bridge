# Windows driver protocol v1

The Python backend opens the private device interface
`{781EF630-72B2-4EAF-A81D-34B3D635A901}` with `GENERIC_WRITE`, no sharing,
and synchronous I/O. Discovery uses Configuration Manager's present interface
list. The driver permits a single connection and grants access to SYSTEM,
administrators, and local interactive users. This is separate from the child
HID interfaces managed by Windows.

`IOCTL_SPENVHID_SUBMIT_REPORT = 0x0022A000` uses `FILE_DEVICE_UNKNOWN`,
function `0x800`, `METHOD_BUFFERED`, and `FILE_WRITE_ACCESS`. The input buffer
is exactly one report including its ID; there is no output. Unknown IOCTLs,
IDs, invalid lengths, reserved bits and out-of-range values are rejected.
Any format change requires coordinated changes to the C and Python contracts.

| Offset | Pen report 1 (`<BBHHHbb`, 10 bytes) |
| --- | --- |
| 0 | Report ID: 1 |
| 1 | Bits: tip=0, barrel=1, in-range=2, invert=3, eraser=4; upper bits zero |
| 2 | X, little-endian uint16, 0–32767 |
| 4 | Y, little-endian uint16, 0–32767 |
| 6 | Pressure, little-endian uint16, 0–32767 |
| 8 | X tilt, signed int8 degrees, −90–90 |
| 9 | Y tilt, signed int8 degrees, −90–90 |

Report 2 (`<BBbb`, 4 bytes) is ID 2, a mouse button byte (left=1,
right=2, middle=4), and two zero relative movement bytes. It supports explicit
left/middle barrel-button mappings without duplicating pen movement. The
normal right-click mapping uses the pen barrel switch; Windows controls its
context-menu behavior. The backend merges buttons mapped to the same action.

Hover and up reports have zero contact/pressure. Eraser hover uses invert;
eraser contact adds eraser. Cancel, proximity exit, final TCP disconnect,
settings remapping and normal close release relevant state. Kernel file
cleanup also releases both reports when the process loses its handle, including
process termination. The last pen coordinates are retained during release.

Reports are validated and submitted on a sequential KMDF queue at passive
level; a wait lock serializes submission with file cleanup. VHF owns buffering,
so input storage can be reused after submission returns. VHF is deleted
synchronously during device cleanup. See Microsoft's
[VHF submission rules](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/vhf/nf-vhf-vhfreadreportsubmit)
and [VHF cleanup rules](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/vhf/nf-vhf-vhfdelete).

The descriptor exposes an integrated Windows Ink pen and an auxiliary mouse.
The logical pressure range does not increase the tablet's physical sensitivity;
it scales the incoming normalized pressure. Linux retains its own ranges.
The vendor/product values are development identifiers, not a certified hardware
identity. No WinTab provider or certification feature report is supplied.
