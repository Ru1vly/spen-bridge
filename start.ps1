$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'server\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run .\install.ps1 first.' }
if ($args.Count -eq 0) {
    & $python (Join-Path $PSScriptRoot 'server\main.py') --gui
} else {
    & $python (Join-Path $PSScriptRoot 'server\main.py') @args
}
exit $LASTEXITCODE
