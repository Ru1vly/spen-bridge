/* S Pen Bridge KMDF entry point. */
#include <ntddk.h>
#include <wdf.h>

DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD SpenVhidEvtDeviceAdd;   // defined in device.c

NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
    )
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;

    WDF_DRIVER_CONFIG_INIT(&config, SpenVhidEvtDeviceAdd);
    // No EvtDriverUnload override needed: KMDF's default object-tree
    // teardown is sufficient - all cleanup happens via the device object's
    // EvtCleanupCallback (added in Phase 2b), not a driver-level one.

    status = WdfDriverCreate(DriverObject, RegistryPath, WDF_NO_OBJECT_ATTRIBUTES, &config, WDF_NO_HANDLE);
    if (!NT_SUCCESS(status)) {
        KdPrint(("spenvhid: WdfDriverCreate failed 0x%x\n", status));
    }
    return status;
}
