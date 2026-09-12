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
    else { Write-Host 'Driver installed. Verify device status in Device Manager, then start S Pen Bridge.' }
} else {
    Write-Host "DevCon not found. Installing via pnputil..."
    & pnputil.exe /add-driver $inf /install
    $result = $LASTEXITCODE
    if ($result -ne 0 -and $result -ne 259 -and $result -ne 3010) {
        throw "pnputil failed with exit code $result. If the initial root device is missing, pass -DevconPath to create root\spenvhid."
    }
    if ($result -eq 3010) { Write-Host 'Restart Windows to finish installing the driver.' }
    else { Write-Host 'Driver package added. Verify device status in Device Manager, then start S Pen Bridge.' }
}
