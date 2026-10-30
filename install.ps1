# Install the desktop application for the current user from this checkout.
# Driver installation is a separate elevated step; see docs/WINDOWS.md.
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$python = Join-Path $repo 'server\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.10-3.14 with its py launcher.'
    }
    $selected = $null
    foreach ($version in @('3.14', '3.13', '3.12', '3.11', '3.10')) {
        try {
            & py "-$version" -c "pass" *> $null
            if ($LASTEXITCODE -eq 0) { $selected = $version; break }
        } catch { continue }
    }
    if (-not $selected) { throw 'Python 3.10-3.14 is required by the pinned Qt runtime.' }
    & py "-$selected" -m venv (Join-Path $repo 'server\.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $python -c "import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] < (3, 15)))"
if ($LASTEXITCODE -ne 0) { throw 'The existing environment needs Python 3.10-3.14. Create a compatible environment before retrying.' }
& $python -m pip install --require-hashes -r (Join-Path $repo 'server\requirements.txt')
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

# USB is loopback-only by default. Wi-Fi is an explicit application setting.
# Configure a private-network firewall rule for the selected port when enabling
# Wi-Fi; do not open a fixed port during an unrelated application install.
Write-Host 'Application installed. Launch S Pen Bridge from Start or run .\start.ps1.'
Write-Host 'The signed virtual HID driver must also be installed; see docs/WINDOWS.md.'
