[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BuildRoot,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Inf2CatPath,
    [string]$SignToolPath,
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredFile([string]$Path, [string]$Name, [string]$ParameterName) {
    if ($Path) {
        $resolved = (Resolve-Path $Path -ErrorAction Stop).Path
        if ([IO.Path]::GetFileName($resolved) -ne $Name) {
            throw "$Name was expected, got $resolved."
        }
        return $resolved
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "$Name was not found. Pass -$ParameterName or add it to PATH." }
    return $command.Source
}

$build = (Resolve-Path $BuildRoot -ErrorAction Stop).Path
$out = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $out | Out-Null

$inf = Get-ChildItem $build -Recurse -Filter spenvhid.inf | Select-Object -First 1
$sys = Get-ChildItem $build -Recurse -Filter spenvhid.sys | Select-Object -First 1
if (-not $inf -or -not $sys) { throw "BuildRoot must contain spenvhid.inf and spenvhid.sys." }

Copy-Item $inf.FullName (Join-Path $out "spenvhid.inf") -Force
Copy-Item $sys.FullName (Join-Path $out "spenvhid.sys") -Force

if ($CertificateThumbprint) {
    $signtool = Resolve-RequiredFile $SignToolPath "signtool.exe" "SignToolPath"
    $cert = Get-ChildItem Cert:\CurrentUser\My\$CertificateThumbprint -ErrorAction Stop
    if (-not $cert) { throw "Certificate $CertificateThumbprint was not found in CurrentUser\My." }

    # Inf2Cat hashes the files it packages. Sign the SYS first so the
    # catalog records the final driver bytes; then sign the catalog itself.
    & $signtool sign /sha1 $CertificateThumbprint /fd sha256 /tr $TimestampUrl /td sha256 (Join-Path $out "spenvhid.sys")
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for spenvhid.sys with exit code $LASTEXITCODE." }
}

$inf2cat = Resolve-RequiredFile $Inf2CatPath "Inf2Cat.exe" "Inf2CatPath"
& $inf2cat "/driver:$out" "/os:10_X64"
if ($LASTEXITCODE -ne 0) { throw "Inf2Cat failed with exit code $LASTEXITCODE." }
$cat = Join-Path $out "spenvhid.cat"
if (-not (Test-Path $cat)) { throw "Inf2Cat did not produce $cat." }

if ($CertificateThumbprint) {
    & $signtool sign /sha1 $CertificateThumbprint /fd sha256 /tr $TimestampUrl /td sha256 $cat
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for spenvhid.cat with exit code $LASTEXITCODE." }
}

$metadata = [ordered]@{
    package = "spenvhid"
    generatedUtc = [DateTime]::UtcNow.ToString("o")
    signed = [bool]$CertificateThumbprint
    files = @("spenvhid.inf", "spenvhid.sys", "spenvhid.cat")
}
$metadata | ConvertTo-Json | Set-Content (Join-Path $out "package.json") -Encoding UTF8
Write-Host "Driver package written to $out"
if (-not $CertificateThumbprint) {
    Write-Warning "Package is unsigned. Sign both SYS and CAT before installing on a normal Windows system."
}
