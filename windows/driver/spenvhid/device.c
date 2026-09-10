/* KMDF source driver: VHF owns HID buffering; the private queue is serialized. */
#include <ntddk.h>
#include <wdf.h>
#include <initguid.h>
#include <vhf.h>
#include "ioctl.h"
#include "report_descriptor.h"

#ifndef _KERNEL_MODE
#error VHF must be compiled with the kernel-mode ABI
#endif

typedef struct _DEVICE_CONTEXT {
    VHFHANDLE Vhf;
    WDFWAITLOCK Lock;
    SPEN_PEN_REPORT LastPen;
} DEVICE_CONTEXT;
WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, SpenGetContext)

EVT_WDF_OBJECT_CONTEXT_CLEANUP SpenDeviceCleanup;
EVT_WDF_FILE_CLEANUP SpenFileCleanup;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL SpenIoControl;
EVT_WDF_DRIVER_DEVICE_ADD SpenVhidEvtDeviceAdd;

static NTSTATUS
SpenSubmit(DEVICE_CONTEXT *Context, PUCHAR Buffer, ULONG Length)
{
    HID_XFER_PACKET packet;
    if (Context->Vhf == NULL) {
        return STATUS_DEVICE_NOT_READY;
    }
    RtlZeroMemory(&packet, sizeof(packet));
    packet.reportBuffer = Buffer;
    packet.reportBufferLen = Length;
    packet.reportId = Buffer[0];
    return VhfReadReportSubmit(Context->Vhf, &packet);
}

VOID
SpenFileCleanup(WDFFILEOBJECT FileObject)
{
    DEVICE_CONTEXT *context = SpenGetContext(WdfFileObjectGetDevice(FileObject));
    SPEN_MOUSE_REPORT mouse = {2, 0, 0, 0};
    WdfWaitLockAcquire(context->Lock, NULL);
    context->LastPen.ReportId = 1;
    context->LastPen.Flags = 0;
    context->LastPen.Pressure = 0;
    (void)SpenSubmit(context, (PUCHAR)&context->LastPen, sizeof(context->LastPen));
    (void)SpenSubmit(context, (PUCHAR)&mouse, sizeof(mouse));
    WdfWaitLockRelease(context->Lock);
}

VOID
SpenDeviceCleanup(WDFOBJECT Object)
{
    DEVICE_CONTEXT *context = SpenGetContext(Object);
    if (context->Vhf != NULL) {
        VhfDelete(context->Vhf, TRUE);
        context->Vhf = NULL;
    }
}

VOID
SpenIoControl(WDFQUEUE Queue, WDFREQUEST Request, size_t OutputLength,
              size_t InputLength, ULONG Code)
{
    DEVICE_CONTEXT *context = SpenGetContext(WdfIoQueueGetDevice(Queue));
    PUCHAR buffer;
    NTSTATUS status;
    SPEN_PEN_REPORT *pen;
    UNREFERENCED_PARAMETER(OutputLength);

    if (Code != IOCTL_SPENVHID_SUBMIT_REPORT) {
        WdfRequestComplete(Request, STATUS_INVALID_DEVICE_REQUEST);
        return;
    }
    status = WdfRequestRetrieveInputBuffer(Request, 1, (PVOID *)&buffer, NULL);
    if (!NT_SUCCESS(status)) {
        WdfRequestComplete(Request, status);
        return;
    }
    if (buffer[0] == 1 && InputLength == sizeof(SPEN_PEN_REPORT)) {
        pen = (SPEN_PEN_REPORT *)buffer;
        if ((pen->Flags & ~31) || pen->X > 32767 || pen->Y > 32767 ||
            pen->Pressure > 32767 || pen->TiltX < -90 || pen->TiltX > 90 ||
            pen->TiltY < -90 || pen->TiltY > 90) {
            WdfRequestComplete(Request, STATUS_INVALID_PARAMETER);
            return;
        }
    } else if (buffer[0] == 2 && InputLength == sizeof(SPEN_MOUSE_REPORT)) {
        if ((buffer[1] & ~7) || buffer[2] || buffer[3]) {
            WdfRequestComplete(Request, STATUS_INVALID_PARAMETER);
            return;
        }
    } else {
        WdfRequestComplete(Request, STATUS_INVALID_PARAMETER);
        return;
    }
    WdfWaitLockAcquire(context->Lock, NULL);
    status = SpenSubmit(context, buffer, (ULONG)InputLength);
    if (NT_SUCCESS(status) && buffer[0] == 1) {
        RtlCopyMemory(&context->LastPen, buffer, sizeof(context->LastPen));
    }
    WdfWaitLockRelease(context->Lock);
    WdfRequestComplete(Request, status);
}

NTSTATUS
SpenVhidEvtDeviceAdd(WDFDRIVER Driver, PWDFDEVICE_INIT DeviceInit)
{
    WDFDEVICE device;
    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_OBJECT_ATTRIBUTES lockAttributes;
    WDF_FILEOBJECT_CONFIG files;
    WDF_IO_QUEUE_CONFIG queue;
    VHF_CONFIG vhf;
    DEVICE_CONTEXT *context;
    NTSTATUS status;
    UNREFERENCED_PARAMETER(Driver);

    WdfDeviceInitSetDeviceType(DeviceInit, FILE_DEVICE_UNKNOWN);
    WdfDeviceInitSetExclusive(DeviceInit, TRUE);
    WDF_FILEOBJECT_CONFIG_INIT(&files, WDF_NO_EVENT_CALLBACK,
                              WDF_NO_EVENT_CALLBACK, SpenFileCleanup);
    WdfDeviceInitSetFileObjectConfig(DeviceInit, &files, WDF_NO_OBJECT_ATTRIBUTES);
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&attributes, DEVICE_CONTEXT);
    attributes.ExecutionLevel = WdfExecutionLevelPassive;
    attributes.EvtCleanupCallback = SpenDeviceCleanup;
    status = WdfDeviceCreate(&DeviceInit, &attributes, &device);
    if (!NT_SUCCESS(status)) return status;
    context = SpenGetContext(device);
    WDF_OBJECT_ATTRIBUTES_INIT(&lockAttributes);
    lockAttributes.ParentObject = device;
    status = WdfWaitLockCreate(&lockAttributes, &context->Lock);
    if (!NT_SUCCESS(status)) return status;

    VHF_CONFIG_INIT(&vhf, WdfDeviceWdmGetDeviceObject(device),
                    (USHORT)sizeof(SpenReportDescriptor), (PUCHAR)SpenReportDescriptor);
    vhf.VendorID = 0x1209;
    vhf.ProductID = 0x5342;
    vhf.VersionNumber = 1;
    status = VhfCreate(&vhf, &context->Vhf);
    if (!NT_SUCCESS(status)) return status;
    status = VhfStart(context->Vhf);
    if (!NT_SUCCESS(status)) return status;

    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queue, WdfIoQueueDispatchSequential);
    queue.EvtIoDeviceControl = SpenIoControl;
    status = WdfIoQueueCreate(device, &queue, WDF_NO_OBJECT_ATTRIBUTES, WDF_NO_HANDLE);
    if (!NT_SUCCESS(status)) return status;
    return WdfDeviceCreateDeviceInterface(device, &GUID_DEVINTERFACE_SPENVHID, NULL);
}
