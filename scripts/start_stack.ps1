# Start the whole local stack after a machine reboot, in dependency order:
#   Postgres (WSL Ubuntu) -> llama-server (:8001) -> backend (:8000) -> job worker
# Everything is launched detached (WMI) so it survives terminal/session teardown.
# Usage:  powershell -NoProfile -File scripts\start_stack.ps1 [-SkipPostgres]
param(
    [switch]$SkipPostgres
)

$ErrorActionPreference = "Continue"

if (-not $SkipPostgres) {
    Write-Host "[1/4] postgres (WSL Ubuntu)..."
    wsl -d Ubuntu -u root -- service postgresql start | Out-Null
    $pg = wsl -d Ubuntu -u root -- service postgresql status
    if ("$pg" -match "online") { Write-Host "      postgres: online" } else { Write-Host "      WARNING: postgres not online: $pg" }
} else {
    Write-Host "[1/4] postgres: skipped"
}

Write-Host "[2/4] llama-server (:8001)..."
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    # --parallel 1: one slot owns the full 8192 context. Multi-slot servers split -c across
    # slots, which caused "Context size has been exceeded" failures on concurrent extractions.
    CommandLine = 'cmd /c D:\PS2\data\llm\llama-server.exe -m D:\PS2\data\llm\qwen2.5-3b-instruct-q4_k_m.gguf --port 8001 -c 8192 -ngl 99 --parallel 1 --host 0.0.0.0 2>>D:\PS2\data\llm\server.err.log'
}
Write-Host "      launched rc=$($r.ReturnValue)"

Write-Host "[3/4] backend (:8000)..."
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = 'cmd /c ""cd /d D:\PS2\backend && D:\PS2\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 1>>D:\PS2\data\uvicorn.out.log 2>>D:\PS2\data\uvicorn.err.log""'
}
Set-Content -Path D:\PS2\backend.pid -Value $r.ProcessId
Write-Host "      launched rc=$($r.ReturnValue)"

Write-Host "[4/4] job worker..."
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = 'cmd /c ""cd /d D:\PS2\backend && D:\PS2\.venv\Scripts\python.exe D:\PS2\scripts\worker.py 1>>D:\PS2\data\worker.out.log 2>>D:\PS2\data\worker.err.log""'
}
Write-Host "      launched rc=$($r.ReturnValue)"

# ---- health checks (backend cold start takes ~30s due to torch import) ----
Write-Host "waiting for services..."
$llamaOk = $false; $beOk = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 2
    if (-not $llamaOk) {
        try { $null = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 2 -UseBasicParsing; $llamaOk = $true } catch { }
    }
    if ($llamaOk -and -not $beOk) {
        try { $null = Invoke-WebRequest -Uri "http://localhost:8000/" -TimeoutSec 2 -UseBasicParsing; $beOk = $true } catch { }
    }
    if ($llamaOk -and $beOk) { break }
}
Write-Host ("llama :8001  " + $(if ($llamaOk) { "OK" } else { "FAILED - check data\llm\server.err.log" }))
Write-Host ("backend :8000 " + $(if ($beOk) { "OK" } else { "FAILED - check data\uvicorn.err.log (cold start can take ~30s; re-run this check)" }))
