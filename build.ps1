#Requires -Version 5.1
<#
build.ps1 — Construye el standalone de Bass Karaoke con PyInstaller.

Uso:
    .\build.ps1                    # build normal (--clean --noconfirm)
    .\build.ps1 -SkipClean         # sin limpiar el caché de build
    .\build.ps1 -Verify            # build + auto-check del exe (BK_VERIFY=1)

El resultado queda en dist/BassKaraoke.exe (single-file). Para desplegarlo en
otro PC copia el exe junto con las carpetas songs/ y models/ (no van
empaquetadas; el build solo copia 2 canciones de ejemplo a dist/songs).

Requiere el venv (.venv) con pyinstaller instalado. Los DLLs de cairo se
toman de GTK2-Runtime (variable GTK2_RUNTIME_BIN para override).
#>
[CmdletBinding()]
param(
    [switch]$SkipClean,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$VenvPy  = Join-Path $Root ".venv\Scripts\python.exe"
$PyInst  = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
$Spec    = Join-Path $Root "build_basic.spec"

if (-not (Test-Path $VenvPy)) {
    throw "No se encontró el venv en $VenvPy — crea uno: uv venv .venv --python 3.10"
}
if (-not (Test-Path $Spec)) {
    throw "No se encontró el spec en $Spec"
}
if (-not (Test-Path $PyInst)) {
    Write-Host "pyinstaller no está en el venv — instalándolo…"
    & $VenvPy -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar pyinstaller" }
}

$Args = @($Spec)
if (-not $SkipClean) { $Args += "--clean" }
$Args += "--noconfirm"

Write-Host "`n=== PyInstaller $($Args -join ' ') ===" -ForegroundColor Cyan
Push-Location $Root
try {
    & $PyInst @Args
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$Exe = Join-Path $Root "dist\BassKaraoke.exe"
if (Test-Path $Exe) {
    $Mb = [math]::Round((Get-Item $Exe).Length / 1MB, 1)
    Write-Host "`nOK — dist\BassKaraoke.exe ($Mb MB)" -ForegroundColor Green
} else {
    Write-Warning "El build terminó pero no se encontró dist\BassKaraoke.exe"
    return
}

if ($Verify) {
    Write-Host "`n=== Auto-check (BK_VERIFY=1) ===" -ForegroundColor Cyan
    $Out  = Join-Path $Root "dist\_verify_out.txt"
    Remove-Item $Out -ErrorAction SilentlyContinue
    $env:BK_VERIFY = "1"
    try {
        $p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
        Start-Sleep -Seconds 12
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    } finally {
        Remove-Item Env:BK_VERIFY -ErrorAction SilentlyContinue
    }
    if (Test-Path $Out) { Get-Content $Out } else { Write-Warning "No se generó _verify_out.txt" }
}