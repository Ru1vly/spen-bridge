#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InfPath,
    [string]$DevconPath
)
$ErrorActionPreference = 'Stop'
$inf = (Resolve-Path $InfPath).Path
if ([IO.Path]::GetFileName($inf) -ne 'spenvhid.inf') { throw 'Expected spenvhid.inf.' }
foreach ($file in @('spenvhid.sys', 'spenvhid.cat')) {
    if (-not (Test-Path (Join-Path (Split-Path $inf) $file))) { throw "Missing packaged $file." }
}

$devcon = $null
if ($DevconPath) {
    $devcon = (Resolve-Path $DevconPath).Path
} else {
    $cmd = Get-Command 'devcon.exe' -ErrorAction SilentlyContinue
    if ($cmd) {
        $devcon = $cmd.Source
    } else {
        $candidates = @(Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\Tools" -Recurse -Filter "devcon.exe" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like "*x64*" })
        if ($candidates.Count -gt 0) {
            $devcon = $candidates[0].FullName
        }
    }
}

$existing = @(Get-PnpDevice | Where-Object { $_.InstanceId -like 'ROOT\SPENVHID\*' })
if ($existing.Count -gt 1) { throw 'Multiple SPen root devices exist. Remove duplicates in Device Manager first.' }

if ($devcon) {
    Write-Host "Using DevCon: $devcon"
    if ($existing.Count -eq 1) {
        & $devcon update $inf 'root\spenvhid'
    } else {
        & $devcon install $inf 'root\spenvhid'
    }
    $result = $LASTEXITCODE
    if ($result -gt 1) { throw "Driver installation failed (DevCon exit $result). Check signing and setupapi.dev.log." }
    if ($result -eq 1) { Write-Host 'Restart Windows to finish installing the driver.' }

} else {
    if ($existing.Count -eq 0) {
        throw 'Initial installation requires DevCon to create root\spenvhid. pnputil only stages packages and cannot create this device. Install the x64 WDK tools, then retry with -DevconPath.'
    }
    Write-Host "Updating the existing root device via pnputil..."
    & pnputil.exe /add-driver $inf /install
    $result = $LASTEXITCODE
    if ($result -ne 0 -and $result -ne 259 -and $result -ne 3010) {
        throw "pnputil failed with exit code $result. If the initial root device is missing, pass -DevconPath to create root\spenvhid."
    }
    if ($result -eq 3010) { Write-Host 'Restart Windows to finish installing the driver.' }

}

$devices = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'ROOT\SPENVHID\*' })
if ($devices.Count -ne 1) {
    throw 'Driver package processed, but exactly one present SPen root device was not found. Check Device Manager and setupapi.dev.log; restart if requested.'
}
if ($devices[0].Status -ne 'OK') {
    throw "SPen root device is present but reports '$($devices[0].Status)'. Resolve signing/device status or restart before using the application."
}
Write-Host 'One present SPen root device reports OK. Application connection and Windows Ink validation are separate checks.'
