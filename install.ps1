# Install the desktop application for the current user from this checkout.
# Driver installation is a separate elevated step; see docs/WINDOWS.md.
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$python = Join-Path $repo 'server\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    & py -3 -m venv (Join-Path $repo 'server\.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required. Install Python and its py launcher.' }
}
& $python -m pip install -r (Join-Path $repo 'server\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$programs = [Environment]::GetFolderPath('Programs')
$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $programs 'S Pen Bridge.lnk'))
$link.TargetPath = Join-Path $repo 'server\.venv\Scripts\pythonw.exe'
$link.Arguments = '"' + (Join-Path $repo 'server\main.py') + '" --gui'
$link.WorkingDirectory = $repo
$icon = Join-Path $repo 'spen_icon.png'
if (Test-Path $icon) {
    $link.IconLocation = $icon
}
$link.Save()

# Configure Windows Firewall rule for Wi-Fi tablet connection if elevated
try {
    $existingRule = Get-NetFirewallRule -DisplayName 'S Pen Bridge' -ErrorAction SilentlyContinue
    if (-not $existingRule) {
        New-NetFirewallRule -DisplayName 'S Pen Bridge' -Direction Inbound -LocalPort 40118 -Protocol TCP -Action Allow -Profile Private, Domain -ErrorAction SilentlyContinue | Out-Null
        Write-Host 'Inbound firewall rule created for port 40118.'
    }
} catch {
    # Non-elevated install: advise user
    Write-Host 'Note: For Wi-Fi connection, ensure Windows Firewall allows incoming TCP port 40118.'
}

Write-Host 'Application installed. Launch S Pen Bridge from Start or run .\start.ps1.'
Write-Host 'The signed virtual HID driver must also be installed; see docs/WINDOWS.md.'
