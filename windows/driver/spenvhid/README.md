# spenvhid - Phase 2a compilation spike

**Status: CI-green as of 2026-09-08** (GitHub Actions run
`windows-2025`/VS2026, workflow run id `34205142253`, branch
`windows-phase2a-driver-spike`). This is **not** a working driver yet -
it exists to answer one question before any real device logic gets
written: does a KMDF driver linking against Microsoft's Virtual HID
Framework (VHF) actually compile and link using the
`Microsoft.Windows.WDK.x64` NuGet package on a GitHub Actions runner?
**Yes** - confirmed by a real, successful build producing a genuine
`spenvhid.sys` artifact (178,749 bytes), not just a green checkmark. See
the Windows Support plan's Phase 2 section for the full design; this
directory covers Phase 2a only. Getting there took 6 real CI iterations
after the first, naive draft - the failures and fixes are documented
below because they're load-bearing knowledge for Phase 2b, not just
history.

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

## Resolved by the real CI run (2026-09-08, 6 iterations to green)

Everything below was a genuinely open risk right up until a real
`windows-2025` runner either confirmed or refuted it - none of this could
have been settled by more reading:

1. **`PlatformToolset=WindowsKernelModeDriver10.0` registration - confirmed
   working.** MSBuild recognized the toolset immediately ("Building
   'spenvhid' with toolset 'WindowsKernelModeDriver10.0' and the
   'Universal' target platform. Using KMDF 1.15.") - the VS "Windows Driver
   Kit" extension component is genuinely present on this runner image today.
2. **`WindowsTargetPlatformVersion=10.0.28000.0` - confirmed it wins** over
   whatever SDK version is preinstalled on the runner; the build correctly
   found the NuGet packages' own `km\wdm.h`/`ntddk.h` tree.
3. **`vhf.h`/`Vhfkm.lib` - confirmed available and correctly linked.**
   `CL.exe` compiled `driver.c device.c` and `link.exe` linked against
   `Vhfkm.lib` with zero errors, producing `spenvhid.sys`. This was Phase
   2a's entire reason to exist, and it's now settled: **VHF is usable from
   this NuGet-only toolchain.** The hand-rolled `IOCTL_HID_*` minidriver
   fallback is not needed.
4. **A real, previously-undocumented packaging quirk in this WDK version**
   (`10.0.28000.2526`): several classic "x86-hosted" driver tools are split
   inconsistently across the package's `c\bin\10.0.28000.0\` folders -
   `stampinf.exe`, `apivalidator.exe`, and `drvcat.exe` only exist under
   `x64\`, while `Inf2Cat.exe` only exists under `x86\` (confirmed by
   extracting the real package). Each one broke the build with a `TRK0005`/
   `MSB6004` "cannot locate" error in turn, in the order the build reached
   them. Fixed by explicitly overriding `InfToolPath` and appending the
   `x64` folder to `ExecutablePath` (without removing the `x86` entry
   `Inf2Cat.exe` still needs - an earlier attempt at a single blanket
   `WDKBinRoot_x86` redirect broke `Inf2Cat.exe` this way). **Not obviously
   documented anywhere online** as of this writing - this may be worth a
   Microsoft Q&A post or a `windows-driver-samples` issue.
5. `DriverTargetPlatform=Universal` triggers an `ApiValidator` step
   (validates the binary only calls DDIs guaranteed on every Windows SKU)
   that also hit the same x86/x64 gap for `apivalidator.exe`. Switched to
   `Desktop` instead, which is also the *correct* target - this driver only
   ever targets desktop Windows 10/11, and the plan explicitly isn't
   pursuing HLK/WHQL/UWD certification.
6. `DPVerifierTask` (INF package verification) and `SignTask` (driver
   test-signing) both ran by default and both failed for reasons unrelated
   to the actual driver (a DLL-load path issue, and a newer signtool
   requiring an explicit `/fd` flag this project never configured).
   Disabled via `SkipPackageVerification=true`/`EnableTestSign=false` -
   correctly so, since both are Phase 2b/4b concerns (test-signing
   specifically needs a real Windows machine with testsigning mode
   enabled - the "human + real Windows hardware only" gate).
7. The exact `OutDir` a `ConfigurationType=Driver` project produces -
   confirmed by the artifact upload succeeding against the
   `x64\Debug\**\` glob.
8. `packages.config` (not `<PackageReference>`) restoring via
   `nuget restore <path> -PackagesDirectory <dir>` - confirmed working
   exactly as documented.

## Still genuinely open (not exercised by a compile-only spike)

1. Whether the classic `WdfCoInstallerNNNNN.dll` INF section is still
   needed for a Windows 10/11-only KMDF driver (see `spenvhid.inf`'s own
   comment) - only matters at real install time, not compile time.
2. Whether `_KERNEL_MODE` is actually defined by this toolset/NuGet
   combination - `VHF_CONFIG` has a different, ABI-incompatible member
   selected by `#ifdef _KERNEL_MODE` (a `PDEVICE_OBJECT` vs. a user-mode
   `HANDLE`). Both are pointer-sized so this wouldn't fail to *compile* if
   wrong, only silently miscompile at runtime - worth a one-time check
   (e.g. a `#pragma message`) before Phase 2b's real `VhfCreate` call
   depends on the kernel-mode branch.
3. Everything genuinely requiring real Windows hardware: does the driver
   actually load (`pnputil /add-driver`, test-signing mode, Device
   Manager showing no Code 52), does it show up to Windows Ink, does a
   live Android -> server -> driver -> Krita stroke land correctly. None
   of that is answerable from CI.

## Next steps

Phase 2a is done. Proceed to Phase 2b per the plan's task list: real VHF
wiring (`VhfCreate`/`VhfStart`, replacing the never-invoked
`SpenVhidProbeVhfConfigCompiles` probe), the IOCTL queue and device
interface, `report_descriptor.h`, `ioctl.h`, `server/backends/
windows_report.py`, `docs/WINDOWS_DRIVER_PROTOCOL.md`, and
`tests/test_windows_report_format.py`. Re-enable `SkipPackageVerification`/
`EnableTestSign` once a real device interface exists for INF verification
to meaningfully check, and once test-signing is being deliberately
exercised on real hardware (Phase 2b's own hard human-only gate).
