# Local deployment helper: start/stop/restart the platform without Docker.
# Usage:  powershell -NoProfile -File scripts\deploy_local.ps1 -Action restart [-Port 8000]
param(
    [ValidateSet("start", "stop", "restart")]
    [string]$Action = "restart",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot          # project root (scripts/..)
$BackendDir = Join-Path $Root "backend"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PidFile = Join-Path $Root "backend.pid"
$DataDir = Join-Path $Root "data"
$StdoutLog = Join-Path $DataDir "uvicorn.log"
$StderrLog = Join-Path $DataDir "uvicorn.err.log"

function Get-RunningPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $pidValue = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $pidValue) { return $null }
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match "python") { return $pidValue }
    return $null
}

function Stop-Server {
    $pidValue = Get-RunningPid
    if ($pidValue) {
        # /T kills the whole tree: the venv python.exe launcher spawns a child interpreter,
        # so killing only the launcher would orphan the real server
        taskkill /PID $pidValue /T /F 2>$null | Out-Null
        Start-Sleep -Seconds 1
        Write-Host "stopped server tree (pid $pidValue)"
    } else {
        Write-Host "no running server (pid file missing or stale)"
    }
    # belt and braces: free the port if anything still holds it
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
        Write-Host "killed leftover listener pid $($c.OwningProcess) on port $Port"
    }
    Start-Sleep -Seconds 1
}

function Start-Server {
    if (-not (Test-Path $VenvPython)) {
        throw "venv python not found at $VenvPython - create the venv first (see README.md)"
    }
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $proc = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port" `
        -WorkingDirectory $BackendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru
    Set-Content -Path $PidFile -Value $proc.Id
    # wait for the API to answer (max ~20s)
    $ok = $false
    foreach ($i in 1..20) {
        Start-Sleep -Milliseconds 1000
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$Port/" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
    }
    if ($ok) {
        Write-Host "platform running: http://localhost:$Port  (pid $($proc.Id), logs in data\uvicorn.err.log)"
    } else {
        Write-Host "WARNING: process started (pid $($proc.Id)) but the API did not answer within 20s - check data\uvicorn.err.log"
    }
}

switch ($Action) {
    "start" { Start-Server }
    "stop" { Stop-Server }
    "restart" { Stop-Server; Start-Server }
}
