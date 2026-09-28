# Local dev deploy: WSL Postgres + backend + worker.
# One-time prerequisites: scripts/wsl_pg_setup.sh installs PG16+pgvector in WSL Ubuntu.
# backend/.env points at postgresql+pg8000://cmpdi:cmpdi@localhost:5432/cmpdi
#
# NOTE: all paths are derived from this script's own folder ($PSScriptRoot), so the
# correct copy of the project starts even if several checkouts exist on disk.

$Root = $PSScriptRoot | Split-Path -Parent
$BackendDir = Join-Path $Root "backend"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PidFile = Join-Path $Root "backend.pid"
$SetupScript = Join-Path $PSScriptRoot "wsl_pg_setup.sh"
$WslPath = ($SetupScript -replace "^([A-Za-z]):", { "/mnt/" + $_.Groups[1].Value.ToLower() }) -replace "\\", "/"

Write-Output "[1/3] Postgres (WSL)..."
wsl -d Ubuntu -u root -- bash $WslPath

# Refuse to start a second backend on :8000 (stale server = stale answers)
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Output "PORT 8000 already in use (PID $($busy.OwningProcess)). Stop that process first."
    Write-Output "  Stop-Process -Id $($busy.OwningProcess) -Force"
    exit 1
}

Write-Output "[2/3] Backend on :8000..."
$backend = Start-Process -FilePath $VenvPython -ArgumentList "-m","uvicorn","app.main:app","--port","8000" -WorkingDirectory $BackendDir -PassThru -WindowStyle Hidden
$backend.Id | Set-Content $PidFile

Write-Output "[3/3] Worker..."
Start-Process -FilePath $VenvPython -ArgumentList (Join-Path $Root "scripts\worker.py"),"--poll","3" -WorkingDirectory $BackendDir -WindowStyle Hidden

Start-Sleep -Seconds 8
try {
    $login = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -Body '{"username":"admin","password":"demo123"}' -ContentType "application/json"
    $h = @{ "X-API-Token" = $login.token }
    $health = Invoke-RestMethod -Uri "http://localhost:8000/query/health" -Headers $h
    Write-Output ("up: db=" + $health.db + " llm=" + $health.llm + " | UI: http://localhost:8000 | login admin/demo123")
} catch {
    Write-Output "check failed - backend may still be starting; open http://localhost:8000"
}
