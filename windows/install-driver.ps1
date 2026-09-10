#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InfPath,
    [Parameter(Mandatory)][string]$DevconPath
)
$ErrorActionPreference = 'Stop'
$inf = (Resolve-Path $InfPath).Path
$devcon = (Resolve-Path $DevconPath).Path
if ([IO.Path]::GetFileName($inf) -ne 'spenvhid.inf') { throw 'Expected spenvhid.inf.' }
foreach ($file in @('spenvhid.sys', 'spenvhid.cat')) {
    if (-not (Test-Path (Join-Path (Split-Path $inf) $file))) { throw "Missing packaged $file." }
}
# DevCon install creates a new root node on every invocation. Update existing
# nodes instead, including currently disconnected nodes, to avoid duplicates.
$existing = @(Get-PnpDevice | Where-Object { $_.InstanceId -like 'ROOT\SPENVHID\*' })
if ($existing.Count -gt 1) { throw 'Multiple SPen root devices exist. Remove duplicates in Device Manager first.' }
if ($existing.Count -eq 1) {
    & $devcon update $inf 'root\spenvhid'
} else {
    & $devcon install $inf 'root\spenvhid'
}
$result = $LASTEXITCODE
if ($result -gt 1) { throw "Driver installation failed (DevCon exit $result). Check signing and setupapi.dev.log." }
if ($result -eq 1) { Write-Host 'Restart Windows to finish installing the driver.' }
else { Write-Host 'Driver installed. Verify device status in Device Manager, then start S Pen Bridge.' }
