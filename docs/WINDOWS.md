# Windows setup and validation

Windows 10/11 x64 has an implemented Windows Ink backend and KMDF/VHF driver.
This is experimental source support: the current driver changes still need a
Windows MSBuild and hardware validation. The C sources compile and link with
Clang/LLD against the pinned WDK on Linux; this does not validate installation. A production-signed installer is not
provided. ARM64 and WinTab are not supported.

## Application

Install Python 3.10+ with the `py` launcher. In PowerShell at the repository root:

```powershell
.\install.ps1
.\start.ps1
# Console mode:
.\start.ps1 --cli
```

The installer (`install.ps1`) performs the following:
1. Creates a local Python virtual environment (`server\.venv`) and installs required packages.
2. Creates a current-user Start Menu shortcut (`S Pen Bridge`) with the application icon.
3. Checks for administrative privileges to create an inbound Windows Firewall rule for port 40118 (`S Pen Bridge Server (TCP-In)`), ensuring Wi-Fi tablet connections work seamlessly.

Keep the checkout in place. If local script execution is blocked, use
`powershell -ExecutionPolicy Bypass -File .\install.ps1` for this invocation.
The server will report a missing-driver error until the driver installation step below is complete.

## Build and install the driver

Use Visual Studio 2026 with the C++ and Windows Driver Kit components, plus
NuGet CLI. The project pins its SDK/WDK packages; restore with NuGet, not dotnet:

```powershell
nuget restore windows\driver\spenvhid\packages.config -PackagesDirectory windows\driver\spenvhid\packages
msbuild windows\driver\spenvhid\spenvhid.sln /p:Configuration=Debug /p:Platform=x64 /m /warnaserror
```

The Windows Driver Build workflow runs the same build and uploads SYS, stamped
INF and CAT files. Unsigned build artifacts cannot load on an ordinary Windows
installation. For development, follow Microsoft's
[test-signing procedure](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/test-signing)
on a dedicated Windows test machine: create a test certificate, sign the SYS
and catalog with SHA-256, trust the certificate on the test machine, enable test
signing and restart. Secure Boot policy can prevent enabling test mode. The
scripts here do not change boot security, install certificates, or sign packages.
Production distribution requires an appropriately Microsoft-signed package.

To create a self-contained package from a local build, use the WDK's
`Inf2Cat.exe`. Add `signtool.exe` to `PATH` and provide a trusted certificate
thumbprint when you want the script to sign both the driver and catalog. The
script signs the SYS, creates a catalog containing that signed SYS hash, then
signs the catalog:

```powershell
.\windows\package-driver.ps1 `
  -BuildRoot windows\driver\spenvhid\x64\Release `
  -OutputDirectory .\dist\spenvhid `
  -Inf2CatPath C:\WDK\bin\10.0.28000.0\x86\Inf2Cat.exe

# Development signing on a test machine:
.\windows\package-driver.ps1 `
  -BuildRoot windows\driver\spenvhid\x64\Debug `
  -OutputDirectory .\dist\spenvhid-debug `
  -Inf2CatPath C:\WDK\bin\10.0.28000.0\x86\Inf2Cat.exe `
  -CertificateThumbprint YOUR_CERTIFICATE_THUMBPRINT
```

The script writes `spenvhid.inf`, `spenvhid.sys`, `spenvhid.cat`, and a small
`package.json` manifest. It never creates or trusts certificates and never
enables test-signing mode automatically. Pass `-SignToolPath` when SignTool is
not on `PATH`; use the matching Windows SDK/WDK `bin` directory, not System32.

Place the signed `spenvhid.sys`, stamped `spenvhid.inf` and `spenvhid.cat` in
one directory. Use an elevated PowerShell:

```powershell
.\windows\install-driver.ps1 -InfPath C:\SPenDriver\spenvhid.inf

# Or pass Devcon explicitly if located elsewhere:
.\windows\install-driver.ps1 -InfPath C:\SPenDriver\spenvhid.inf -DevconPath C:\Tools\devcon.exe
```

This creates the root device on first install and updates it thereafter.
DevCon is automatically located from WDK install paths or PATH if present; otherwise `pnputil` is used.
The INF installs VHF as the required lower filter, following Microsoft's
[VHF installation contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/virtual-hid-framework--vhf-).

Verify **S Pen Bridge Virtual HID Tablet** in Device Manager has no error,
and that its HID pen child appears. Start the application as your normal user.
Only one bridge instance can own the device at a time.

After installation, run the automated device/interface smoke check from an
elevated PowerShell:

```powershell
.\windows\validate-driver.ps1
```

It checks the root PnP node, service registration, and a neutral report through
the private interface. Use `-SkipTransport` when validating only installation.

## Connect and draw

Install the Android APK and enable USB debugging. Install Android platform-tools
and put `adb.exe` on PATH. With the server listening:

```powershell
adb reverse tcp:40118 tcp:40118
```

Use USB mode in the Android app. For Wi-Fi, enter the PC's LAN IP and ensure the
inbound port 40118 is allowed through Windows Firewall (configured automatically by
`install.ps1` if run as administrator, or configurable in Advanced Firewall Settings).
Use only a trusted LAN.

Configure drawing applications for Windows Ink (for example Krita's Windows
8+ Pointer Input setting). There is no WinTab emulation. Windows controls the
pen's display association; start with a single screen. Use Windows Tablet PC
Settings to associate the pen with the intended display. Application mapping
scales report coordinates, but full-desktop/mixed-DPI behavior needs validation
against that Windows association and is not yet guaranteed.

With the server running, focus a drawing canvas and run:

```powershell
server\.venv\Scripts\python.exe server\test_synthetic.py
```

Both stored Linux device modes use the same Windows Ink device; Linux direct
input controls are hidden. Device naming is fixed by the installed driver.

## Validation and troubleshooting

Run portable tests with `server\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
Before treating the driver as release-ready, validate on Windows:

- Build Debug and Release, verify the stamped INF, sign and install the package.
- Confirm normal-user access, exclusive ownership and clean uninstall/reinstall.
- Draw with changing pressure/tilt, hover, lift, cancel, eraser and barrel buttons.
- Disconnect USB/Wi-Fi or terminate Python mid-stroke: contact/buttons must release.
- Switch profiles, stop/start the server, sleep/resume, and disable/enable the device.
- Check target display mapping, negative monitor origins and mixed DPI.

Driver missing: check the root device and VHF child in Device Manager. Code 52:
check signing. Installation failures: inspect `%SystemRoot%\inf\setupapi.dev.log`.
Access denied/sharing violation: close other bridge instances and verify the
installed package contains the current security descriptor. Driver removal while
running produces an I/O error; reinstall/re-enable, then restart the server.

To remove the driver, stop the bridge and run elevated PowerShell:
- If DevCon is installed: `devcon remove "root\spenvhid"`
- To remove the staged driver package: locate its published name with `pnputil /enum-drivers` (e.g. `oemNN.inf`), then remove it with `pnputil /delete-driver oemNN.inf /uninstall /force`.

Remove the Start Menu shortcut and checkout to uninstall the application; settings remain under `%APPDATA%\spen-bridge`.
