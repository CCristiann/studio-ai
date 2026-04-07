# Install the FL Studio MIDI script for Studio AI on Windows.
#
# Copies the bridge scripts to FL Studio's Hardware directory so they
# appear in Options -> MIDI Settings as "Studio AI".
#
# Usage (from PowerShell):
#   .\scripts\install-fl-script.ps1

$ErrorActionPreference = "Stop"

$RootDir      = Resolve-Path (Join-Path $PSScriptRoot "..")
$ScriptSrc    = Join-Path $RootDir "bridge\fl_studio\device_studio_ai.py"
$HandlersSrc  = Join-Path $RootDir "bridge\fl_studio\handlers_organize.py"
$TransportSrc = Join-Path $RootDir "bridge\fl_studio\ipc_transport.py"

$FlHardwareDir = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware"
$DestDir       = Join-Path $FlHardwareDir "Studio AI"

foreach ($src in @($ScriptSrc, $HandlersSrc, $TransportSrc)) {
    if (-not (Test-Path $src)) {
        Write-Host "Source not found: $src" -ForegroundColor Red
        exit 1
    }
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

Copy-Item $ScriptSrc    (Join-Path $DestDir "device_studio_ai.py") -Force
Copy-Item $HandlersSrc  (Join-Path $DestDir "handlers_organize.py") -Force
Copy-Item $TransportSrc (Join-Path $DestDir "ipc_transport.py")    -Force

Write-Host "FL Studio MIDI scripts installed to:" -ForegroundColor Green
Write-Host "  $(Join-Path $DestDir 'device_studio_ai.py')"
Write-Host "  $(Join-Path $DestDir 'handlers_organize.py')"
Write-Host "  $(Join-Path $DestDir 'ipc_transport.py')"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open FL Studio"
Write-Host "  2. Options -> MIDI Settings"
Write-Host "  3. Under 'Input', select any available port"
Write-Host "  4. Under 'Controller type', select 'Studio AI'"
Write-Host "  5. Click the green enable button"
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
