<#
.SYNOPSIS
    Arranca/para SonarQube Community Build y lanza el análisis del proyecto.

.DESCRIPTION
    Instalación local sin Docker: ZIP oficial + SonarScanner CLI.
    Requiere JDK 17+ (probado con JDK 21 de Adoptium).

.EXAMPLE
    .\scripts\sonar.ps1 start
    .\scripts\sonar.ps1 scan
    .\scripts\sonar.ps1 status
    .\scripts\sonar.ps1 stop
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'scan', 'open')]
    [string]$Action = 'status',

    [string]$Token = $env:SONAR_TOKEN
)

$ErrorActionPreference = 'Stop'

$SonarHome   = if ($env:SONAR_HOME) { $env:SONAR_HOME } else { 'C:\sonar\sonarqube' }
$ScannerHome = if ($env:SONAR_SCANNER_HOME) { $env:SONAR_SCANNER_HOME } else { 'C:\sonar\sonar-scanner' }
$RepoRoot    = Split-Path -Parent $PSScriptRoot
$Url         = 'http://localhost:9000'

function Get-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { return $env:JAVA_HOME }
    $candidates = @(
        'C:\Program Files\Eclipse Adoptium\jdk-21*',
        'C:\Program Files\Eclipse Adoptium\jdk-17*',
        'C:\Program Files\Java\jdk-21*',
        'C:\Program Files\Microsoft\jdk-21*'
    )
    foreach ($pattern in $candidates) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    throw "No se encontro un JDK 17+. Instala Temurin 21 o define JAVA_HOME."
}

# SonarQube ignora JAVA_HOME: usa SONAR_JAVA_PATH o el java.exe del PATH.
function Set-SonarJava {
    $home_ = Get-JavaHome
    $env:JAVA_HOME = $home_
    $env:SONAR_JAVA_PATH = Join-Path $home_ 'bin\java.exe'
    Write-Verbose "Java: $($env:SONAR_JAVA_PATH)"
}

function Test-ServerUp {
    try {
        $r = Invoke-RestMethod -Uri "$Url/api/system/status" -TimeoutSec 3
        return $r.status -eq 'UP'
    } catch { return $false }
}

function Wait-Server([int]$TimeoutSec = 300) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-ServerUp) { return $true }
        Start-Sleep -Seconds 5
        Write-Host ("  ... esperando ({0:N0}s)" -f $sw.Elapsed.TotalSeconds)
    }
    return $false
}

switch ($Action) {

    'start' {
        if (Test-ServerUp) { Write-Host "SonarQube ya esta arriba en $Url" -ForegroundColor Green; break }
        Set-SonarJava
        $bat = Join-Path $SonarHome 'bin\windows-x86-64\StartSonar.bat'
        if (-not (Test-Path $bat)) { throw "No existe $bat. Ajusta SONAR_HOME." }
        Write-Host "Arrancando SonarQube desde $SonarHome ..."
        Start-Process -FilePath $bat -WorkingDirectory (Split-Path $bat) -WindowStyle Minimized
        if (Wait-Server) {
            Write-Host "SonarQube operativo en $Url (admin/admin la primera vez)" -ForegroundColor Green
        } else {
            Write-Warning "No respondio en 5 min. Revisa $SonarHome\logs\sonar.log"
        }
    }

    'stop' {
        $procs = Get-CimInstance Win32_Process -Filter "name='java.exe'" |
            Where-Object { $_.CommandLine -like '*org.sonar.application.App*' }
        if (-not $procs) { Write-Host "SonarQube no estaba corriendo."; break }
        foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force }
        Write-Host "SonarQube detenido (PID $($procs.ProcessId -join ', '))."
    }

    'status' {
        if (Test-ServerUp) {
            $v = Invoke-RestMethod -Uri "$Url/api/server/version" -TimeoutSec 3
            Write-Host "UP  version $v  ->  $Url" -ForegroundColor Green
        } else {
            Write-Host "DOWN (usa: scripts\sonar.ps1 start)" -ForegroundColor Yellow
        }
    }

    'open' {
        Start-Process $Url
    }

    'scan' {
        if (-not (Test-ServerUp)) { throw "SonarQube no responde en $Url. Ejecuta: scripts\sonar.ps1 start" }
        if (-not $Token) { throw "Falta SONAR_TOKEN. Genera un token de usuario en $Url/account/security y exportalo." }

        $env:JAVA_HOME = Get-JavaHome
        Push-Location $RepoRoot
        try {
            Write-Host "1/2 Cobertura (pytest-cov) ..."
            $py = ".\.venv\Scripts\python.exe"
            # cmd /c evita que los warnings de stderr rompan ErrorActionPreference=Stop
            cmd /c "`"$py`" -m pytest -q --cov=bass_karaoke --cov-report=xml 2>&1" |
                Select-Object -Last 4
            if (-not (Test-Path 'coverage.xml')) { throw "pytest-cov no genero coverage.xml" }

            $scanner = Join-Path $ScannerHome 'bin\sonar-scanner.bat'
            if (-not (Test-Path $scanner)) { throw "No existe $scanner. Define SONAR_SCANNER_HOME." }

            Write-Host "2/2 Analisis SonarQube ..."
            & $scanner "-Dsonar.host.url=$Url" "-Dsonar.token=$Token"
            if ($LASTEXITCODE -ne 0) { throw "sonar-scanner fallo con codigo $LASTEXITCODE" }

            Write-Host "Listo: $Url/dashboard?id=bass-karaoke" -ForegroundColor Green
        } finally {
            Pop-Location
        }
    }
}
