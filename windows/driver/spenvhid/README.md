# spenvhid - Phase 2a compilation spike

This is **not** a working driver yet. It exists to answer one question before
any real device logic gets written: does a KMDF driver linking against
Microsoft's Virtual HID Framework (VHF) actually compile and link using the
`Microsoft.Windows.WDK.x64` NuGet package on a GitHub Actions runner? See the
Windows Support plan's Phase 2 section for the full design; this directory
covers Phase 2a only.

## What's here (Phase 2a scope)

- `driver.c` - `DriverEntry` only.
- `device.c` - `SpenVhidEvtDeviceAdd` that does nothing but `WdfDeviceCreate`,
  plus `SpenVhidProbeVhfConfigCompiles`: a function invoked once from
  `EvtDeviceAdd` but otherwise unused at runtime, whose only job is forcing
  the compiler/linker to touch `vhf.h`'s types and `Vhfkm.lib`'s exports. No
  VHF instance is actually created, no IOCTL queue exists, no device
  interface is exposed - that's all Phase 2b.
- `spenvhid.inf` - root-enumerated software device INF (final version, since
  it doesn't depend on the IOCTL contract).
- `spenvhid.vcxproj` / `.sln` / `packages.config` - minimal KMDF driver
  project wired to the NuGet-restored WDK via the standard MSBuild
  "native package" import idiom.

## Resolved WDK NuGet version

**`Microsoft.Windows.WDK.x64` 10.0.28000.2526** (published 2026-07-24),
confirmed current via nuget.org as of 2026-09-08. It depends on
`Microsoft.Windows.SDK.CPP.x64 >= 10.0.28000, < 10.0.28001`; `packages.config`
pins all three (`Microsoft.Windows.WDK.x64`, `Microsoft.Windows.SDK.CPP`,
`Microsoft.Windows.SDK.CPP.x64`) to this same version string, matching the
pattern Microsoft's own driver-samples repo uses for pinned NuGet builds -
confirmed required, not just conventional: `Microsoft.Windows.SDK.CPP.x64`
10.0.28000.2526 declares an *exact* dependency on `Microsoft.Windows.SDK.cpp`
`= 10.0.28000.2526`, so the three versions can't drift independently.

**Verified by downloading and extracting the real `.nupkg` files during
Phase 2a review** (not from memory or docs alone): `vhf.h` lives inside the
`Microsoft.Windows.SDK.CPP` package (`c\Include\10.0.28000.0\shared\vhf.h`),
**not** inside `Microsoft.Windows.WDK.x64` - that package's own `shared`
include folder has no VHF header at all. `Vhfkm.lib` **is** in the WDK.x64
package (`c\Lib\10.0.28000.0\km\x64\vhfkm.lib`). This is why the `.vcxproj`
imports all three packages' `build\native\*.props`, not just WDK.x64's -
an earlier draft of this file only imported WDK.x64's and would have failed
to resolve `vhf.h` at all. Of the three, only `Microsoft.Windows.SDK.CPP`
ships a `build\native\*.targets` alongside its `.props`; `WDK.x64` ships
`.props` only (its real driver build logic is pulled in through the
`PlatformToolset`'s own `Toolset.props`/`.targets` chain instead), and
`SDK.CPP.x64`'s `.targets` presence wasn't checked (only its `.props` was
confirmed) - the `.vcxproj` only imports `.targets` where confirmed to
exist, guarded by `Exists()` either way.

Confirmed directly from Microsoft's current docs (`learn.microsoft.com/.../install-the-wdk-using-nuget`,
updated 2026-07-24):
- This NuGet package requires **Visual Studio 2026**.
- **`dotnet restore` explicitly does not work** with this package - the docs
  say so directly. Must use `nuget.exe restore` against `packages.config`.
- GitHub's `windows-latest` runner moved to Windows Server 2025 + VS2026 in
  June 2026 and is still current - but the workflow pins `windows-2025`
  explicitly rather than the floating alias, since this whole dependency
  chain has already changed once this year.

## Resolved during Phase 2a review (verified against the real packages/samples)

A review pass actually downloaded and extracted the three pinned `.nupkg`
files and fetched Microsoft's own `Windows-driver-samples` repo live, rather
than reasoning from docs/memory alone. This resolved several things that
were open questions in an earlier draft:

- `vhf.h` location and the missing `SDK.CPP`/`SDK.CPP.x64` imports (see
  above) - **fixed**, was a real blocking gap.
- The `packages\Microsoft.Windows.WDK.x64.<version>\build\native\...props`
  path itself - **confirmed correct**, byte-for-byte against the real
  package and against Microsoft's own `Directory.Build.props`.
- `ConfigurationType=Driver` / `DriverType=KMDF` - **confirmed correct**
  against the WDK package's own `WindowsDriver.KernelMode.props`.
  `DriverTargetPlatform` was originally `Universal` but switched to
  `Desktop` after a real CI run (see below) - this driver only ever
  targets desktop Windows 10/11, so `Universal`'s extra DDI-compliance
  validation was never the right target anyway.
- Identical-version pinning across all three `packages.config` entries -
  **confirmed required** by the real dependency graph, not just conventional
  (see above).
- `device.c` had two real compile-breaking bugs, now fixed: `(PHID_REPORT_DESCRIPTOR)`
  isn't a real vhf.h type (`VHF_CONFIG_INIT`'s descriptor parameter is
  `PUCHAR`) - it was a locally-scoped typedef in an unrelated, unused sample
  - and `UNREFERENCED_PARAMETER(Driver)` came before this file's variable
  declarations, which is a hard C89 parse error (no `/std:c11`/`:c17` is set,
  so `.c` files here compile as ANSI C89) rather than a warning.
- `WindowsTargetPlatformVersion` was left floating as `10.0` - now pinned to
  `10.0.28000.0` to match the NuGet packages' own internal content version,
  since a floating version could resolve against the runner's differently
  -versioned preinstalled SDK instead (see the `.vcxproj`'s own comment).

## Open risks (still not resolved - this is what CI is for)

1. **`PlatformToolset=WindowsKernelModeDriver10.0`'s registration is not
   actually NuGet-sourced.** That toolset name is made known to MSBuild by
   the Visual Studio "Windows Driver Kit" extension component, not by these
   NuGet packages (confirmed: the WDK package's own `.props` never touches
   `PlatformToolset` registration, and a real independent project hit
   `MSB8020: build tools for WindowsKernelModeDriver10.0 cannot be found`
   without that VS component). `windows-2025` CI runners are confirmed to
   have that component preinstalled today (`actions/runner-images#14263`)
   even though the WDK *content* is deliberately absent - which is exactly
   the gap these NuGet packages fill. If that component is ever dropped too,
   this project would need a hand-authored `Toolset.props`/`.targets` shim.
2. **Whether `WindowsTargetPlatformVersion=10.0.28000.0` actually wins**
   over the runner's preinstalled SDK during real MSBuild property
   evaluation - the WDK package's `.props` only sets `WindowsSdkDir` when it
   isn't already set by something else, and `microsoft/setup-msbuild@v2`
   doesn't touch `WindowsSdkDir`/`INCLUDE`/`LIB` itself. Only a real CI run
   proves the resolution order.
3. **`packages.config` vs `<PackageReference>`.** Following Microsoft's own
   `Windows-driver-samples` "Building Locally" doc and CI/CD guidance, which
   both use `packages.config` + `nuget restore`, not `<PackageReference>`.
4. Whether the classic `WdfCoInstallerNNNNN.dll` INF section is still needed
   for a Windows 10/11-only KMDF driver (see `spenvhid.inf`'s own comment).
5. The exact `OutDir` a `ConfigurationType=Driver` project produces (the CI
   workflow globs broadly under `x64\Debug\**\` for the artifact upload
   rather than assuming an exact nested path, precisely because this wasn't
   confirmed).
6. Whether `_KERNEL_MODE` is actually defined by this toolset/NuGet
   combination - `VHF_CONFIG` has a different, ABI-incompatible member
   selected by `#ifdef _KERNEL_MODE` (a `PDEVICE_OBJECT` vs. a user-mode
   `HANDLE`). Both are pointer-sized so this wouldn't fail to *compile* if
   wrong, only silently miscompile - not a Phase 2a blocker but worth a
   one-time check (e.g. a `#pragma message`) once real CI runs, before
   Phase 2b's `VhfCreate` call depends on the kernel-mode branch.

## Next steps (Phase 2a task list)

1. Push this skeleton, watch `.github/workflows/windows-driver-build.yml`.
2. If NuGet restore fails to locate WDK build customizations: try
   `<PackageReference>` instead of `packages.config`, or a scripted WDK MSI
   install as a documented fallback.
3. Green build (through the link step) = `vhf.h`/`Vhfkm.lib` confirmed
   available and correctly referenced; proceed to Phase 2b (real VHF wiring,
   IOCTL queue, device interface, `report_descriptor.h`, `ioctl.h`,
   `windows_report.py`, `docs/WINDOWS_DRIVER_PROTOCOL.md`).
4. Red build at the link step specifically = branch to the hand-rolled
   `IOCTL_HID_*` minidriver fallback instead of VHF.
