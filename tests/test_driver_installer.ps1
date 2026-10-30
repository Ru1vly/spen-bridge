# Portable installer logic checks. Every PnP/installer command is replaced.
# The actual script's administrator requirement remains intact in production.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$source = [IO.File]::ReadAllText((Join-Path $root 'windows/install-driver.ps1'))
$source = $source -replace '(?im)^#Requires[ \t]+-RunAsAdministrator[ \t]*\r?\n', ''
$body = [scriptblock]::Create($source)
$temp = Join-Path ([IO.Path]::GetTempPath()) ('spen-installer-test-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
$inf = Join-Path $temp 'spenvhid.inf'
foreach ($name in @('spenvhid.inf', 'spenvhid.sys', 'spenvhid.cat')) {
    [IO.File]::WriteAllText((Join-Path $temp $name), 'Explicitly fake test package; never load.')
}
$fakeDevcon = Join-Path $temp 'fake-devcon.ps1'
[IO.File]::WriteAllText($fakeDevcon, @'
param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Arguments)
$global:SPenInstallerTestState.DevconCalls++
$global:SPenInstallerTestState.DevconAction = $Arguments[0]
$global:LASTEXITCODE = $global:SPenInstallerTestState.ExitCode
'@)

function Invoke-InstallerCase {
    param($Case)
    $node = [pscustomobject]@{ InstanceId = 'ROOT\SPENVHID\0000'; Status = $Case.Status }
    $global:SPenInstallerTestState = @{
        Existing = @(); Present = @(); ExitCode = $Case.ExitCode
        PnpCalls = 0; DevconCalls = 0; DevconAction = ''
    }
    if ($Case.Existing -ge 1) { $global:SPenInstallerTestState.Existing = @($node) }
    if ($Case.Existing -ge 2) { $global:SPenInstallerTestState.Existing += $node }
    if ($Case.Present) { $global:SPenInstallerTestState.Present = @($node) }

    function Get-PnpDevice {
        [CmdletBinding()]param([switch]$PresentOnly)
        if ($PresentOnly) { $global:SPenInstallerTestState.Present }
        else { $global:SPenInstallerTestState.Existing }
    }
    function Get-Command {
        [CmdletBinding()]param([Parameter(Position=0)][string]$Name)
        if ($Name -eq 'devcon.exe') { return }
        Microsoft.PowerShell.Core\Get-Command @PSBoundParameters
    }
    function Get-ChildItem {
        [CmdletBinding()]param([string]$Path, [switch]$Recurse, [string]$Filter)
        # Never discover or execute a real WDK tool on a Windows test runner.
        if ($Path -like 'C:\Program Files (x86)\Windows Kits\10\Tools*') { return }
        Microsoft.PowerShell.Management\Get-ChildItem @PSBoundParameters
    }
    function pnputil.exe {
        param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Arguments)
        $global:SPenInstallerTestState.PnpCalls++
        $global:LASTEXITCODE = $global:SPenInstallerTestState.ExitCode
    }
    $arguments = @{ InfPath = $inf }
    if ($Case.Devcon) { $arguments.DevconPath = $fakeDevcon }
    $failure = ''
    try { & $body @arguments 6>$null | Out-Null }
    catch { $failure = $_.Exception.Message }
    if ($Case.Error) {
        if (-not $failure.Contains($Case.Error)) { throw "$($Case.Name): expected '$($Case.Error)', received '$failure'" }
    } elseif ($failure) { throw "$($Case.Name): unexpected failure '$failure'" }
    $state = $global:SPenInstallerTestState
    if ($state.PnpCalls -ne $Case.PnpCalls -or $state.DevconCalls -ne $Case.DevconCalls) {
        throw "$($Case.Name): unexpected native-command routing"
    }
    if ($Case.Action -and $state.DevconAction -ne $Case.Action) { throw "$($Case.Name): incorrect DevCon action" }
    [pscustomobject]@{ case = $Case.Name; passed = $true; native_commands_mocked = $true }
}

try {
    $cases = @(
        @{ Name='first install needs creator'; Existing=0; Present=$false; Status='OK'; Devcon=$false; ExitCode=0; Error='Initial installation requires DevCon'; PnpCalls=0; DevconCalls=0 },
        @{ Name='package staging is not device creation'; Existing=1; Present=$false; Status='OK'; Devcon=$false; ExitCode=0; Error='exactly one present'; PnpCalls=1; DevconCalls=0 },
        @{ Name='update present healthy node'; Existing=1; Present=$true; Status='OK'; Devcon=$false; ExitCode=0; Error=''; PnpCalls=1; DevconCalls=0 },
        @{ Name='creator installs first root node'; Existing=0; Present=$true; Status='OK'; Devcon=$true; ExitCode=0; Error=''; PnpCalls=0; DevconCalls=1; Action='install' },
        @{ Name='duplicate roots rejected'; Existing=2; Present=$true; Status='OK'; Devcon=$true; ExitCode=0; Error='Multiple SPen root devices'; PnpCalls=0; DevconCalls=0 },
        @{ Name='unhealthy node rejected'; Existing=1; Present=$true; Status='Error'; Devcon=$true; ExitCode=0; Error="reports 'Error'"; PnpCalls=0; DevconCalls=1; Action='update' },
        @{ Name='creator failure rejected'; Existing=0; Present=$false; Status='OK'; Devcon=$true; ExitCode=2; Error='Driver installation failed'; PnpCalls=0; DevconCalls=1; Action='install' },
        @{ Name='pnputil failure rejected'; Existing=1; Present=$true; Status='OK'; Devcon=$false; ExitCode=5; Error='pnputil failed'; PnpCalls=1; DevconCalls=0 }
    )
    $results = @($cases | ForEach-Object { Invoke-InstallerCase $_ })
    $results | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $root 'audit/evidence/remediation-powershell-installer.json')
    Write-Output "$($results.Count) installer logic cases passed; all native commands mocked."
} finally {
    Remove-Variable -Name SPenInstallerTestState -Scope Global -ErrorAction SilentlyContinue
    [IO.Directory]::Delete($temp, $true)
}
