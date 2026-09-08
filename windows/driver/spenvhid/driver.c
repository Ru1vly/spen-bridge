/*
 * spenvhid - S Pen Bridge Windows virtual HID tablet driver.
 *
 * Phase 2a scope: prove the KMDF + VHF toolchain resolves, compiles, and
 * links via the NuGet-restored WDK before any real device logic exists.
 * DriverEntry here is deliberately minimal - all device setup lives in
 * device.c's SpenVhidEvtDeviceAdd, which creates the device object and then
 * calls a VHF_CONFIG probe (SpenVhidProbeVhfConfigCompiles) that is never
 * invoked at runtime by anything else - its only job is forcing the
 * compiler/linker to resolve vhf.h/Vhfkm.lib. Real VHF wiring (VhfCreate),
 * the IOCTL queue, and the device interface are Phase 2b - see the design
 * notes in windows/driver/spenvhid/README.md.
 */
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
