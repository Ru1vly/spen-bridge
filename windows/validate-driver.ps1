[CmdletBinding()]
param(
    [string]$PythonPath = "$PSScriptRoot\..\server\.venv\Scripts\python.exe",
    [switch]$SkipTransport
)

$ErrorActionPreference = "Stop"

$devices = @(Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -like 'ROOT\SPENVHID\*' -or $_.FriendlyName -eq 'S Pen Bridge Virtual HID Tablet'
})
if (-not $devices) { throw 'S Pen Bridge root device is not present. Install the signed package first.' }
$bad = @($devices | Where-Object { $_.Status -ne 'OK' })
if ($bad) {
    $bad | Format-Table Status, Class, FriendlyName, InstanceId | Out-String | Write-Error
    throw 'S Pen Bridge has a device error. Check Device Manager and setupapi.dev.log.'
}

$service = Get-Service spenvhid -ErrorAction SilentlyContinue
if (-not $service) { throw 'The spenvhid service is not installed.' }
Write-Host "Device OK: $($devices.Count) PnP node(s); service state: $($service.Status)"

if (-not $SkipTransport) {
    if (-not (Test-Path $PythonPath)) { throw "Python was not found at $PythonPath. Pass -PythonPath or use -SkipTransport." }
    $repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $code = @'
from server.backends.windows_report import pack_pen
from server.backends.windows_transport import DriverConnection
c = DriverConnection()
try:
    c.submit(pack_pen())
finally:
    c.close()
print("Private HID interface accepted a neutral report")
'@
    Push-Location $repo
    try { & $PythonPath -c $code }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Python transport smoke test failed with exit code $LASTEXITCODE." }
}

Write-Host 'Driver validation passed. Continue with pressure, tilt, eraser, buttons, disconnect, and display-mapping tests.'
