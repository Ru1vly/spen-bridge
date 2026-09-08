/*
 * spenvhid device setup - Phase 2a minimal version.
 *
 * EvtDeviceAdd does nothing but create the device object: no VHF instance,
 * no IOCTL queue, no device interface. Those all land in Phase 2b once this
 * minimal skeleton is confirmed to compile and link on windows-2025/VS2026
 * CI (see .github/workflows/windows-driver-build.yml).
 *
 * SpenVhidProbeVhfConfigCompiles below exists to force the compiler/linker
 * to actually touch VHF's types and macros, not just parse the include. It
 * is never called at runtime by anything other than EvtDeviceAdd itself.
 * The dummy descriptor bytes below are not a real HID report descriptor -
 * that's Phase 2b's report_descriptor.h.
 */
#include <ntddk.h>
#include <wdf.h>
#include <vhf.h>              // lives in the Microsoft.Windows.SDK.CPP NuGet
                               // package, NOT Microsoft.Windows.WDK.x64 -
                               // confirmed by extracting the real packages;
                               // see spenvhid.vcxproj's top comment + README.md

static void
SpenVhidProbeVhfConfigCompiles(
    _In_ WDFDEVICE Device
    )
{
    static const UCHAR dummyDescriptor[] = { 0x06, 0x00, 0xFF, 0xC0 };
    VHF_CONFIG config;

    // VHF_CONFIG_INIT's real ReportDescriptor parameter is PUCHAR, not a
    // PHID_REPORT_DESCRIPTOR type - that name doesn't exist in vhf.h at all
    // (it's a local typedef the unrelated vhidmini2 sample defines for
    // itself). Confirmed against learn.microsoft.com's VHF_CONFIG_INIT/
    // _VHF_CONFIG reference during the Phase 2a review pass.
    VHF_CONFIG_INIT(
        &config,
        WdfDeviceWdmGetDeviceObject(Device),
        sizeof(dummyDescriptor),
        (PUCHAR)dummyDescriptor);
}

NTSTATUS
SpenVhidEvtDeviceAdd(
    _In_ WDFDRIVER Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
    )
{
    WDFDEVICE device;
    NTSTATUS  status;

    // Declarations must precede statements here: this file compiles as
    // ANSI C89 by default (no /std:c11/:c17 set), which is a hard parse
    // error, not a /W4 warning, if UNREFERENCED_PARAMETER(Driver) came
    // first - confirmed against Microsoft's vhidmini2 sample, which places
    // its own UNREFERENCED_PARAMETER calls last for the same reason.
    UNREFERENCED_PARAMETER(Driver);

    status = WdfDeviceCreate(&DeviceInit, WDF_NO_OBJECT_ATTRIBUTES, &device);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    SpenVhidProbeVhfConfigCompiles(device);

    return STATUS_SUCCESS;
}
