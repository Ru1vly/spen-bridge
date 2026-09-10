#pragma once

/* Private interface, not GUID_DEVINTERFACE_HID. See WINDOWS_DRIVER_PROTOCOL.md. */
DEFINE_GUID(GUID_DEVINTERFACE_SPENVHID,
    0x781ef630, 0x72b2, 0x4eaf, 0xa8, 0x1d, 0x34, 0xb3, 0xd6, 0x35, 0xa9, 0x01);
#define IOCTL_SPENVHID_SUBMIT_REPORT CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_WRITE_ACCESS)

#pragma pack(push, 1)
typedef struct _SPEN_PEN_REPORT {
    UCHAR ReportId;
    UCHAR Flags;
    USHORT X;
    USHORT Y;
    USHORT Pressure;
    CHAR TiltX;
    CHAR TiltY;
} SPEN_PEN_REPORT;

typedef struct _SPEN_MOUSE_REPORT {
    UCHAR ReportId;
    UCHAR Buttons;
    CHAR X;
    CHAR Y;
} SPEN_MOUSE_REPORT;
#pragma pack(pop)
C_ASSERT(sizeof(SPEN_PEN_REPORT) == 10);
C_ASSERT(sizeof(SPEN_MOUSE_REPORT) == 4);
