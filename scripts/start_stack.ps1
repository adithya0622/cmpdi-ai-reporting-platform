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

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PidFile = Join-Path $Root "backend.pid"
$DataDir = Join-Path $Root "data"
$LlmDir = Join-Path $DataDir "llm"
$WorkerPy = Join-Path $Root "scripts\worker.py"

Write-Host "[2/4] llama-server (:8001)..."
$llamaExe = Join-Path $LlmDir "llama-server.exe"
$qwen3 = Join-Path $LlmDir "Qwen3-8B-Q4_K_M.gguf"
$qwen25 = Join-Path $LlmDir "qwen2.5-3b-instruct-q4_k_m.gguf"
$llamaLog = Join-Path $LlmDir "server.err.log"
if (Test-Path $qwen3) {
    $llamaModel = $qwen3
    $llamaArgs = "--port 8001 -c 8192 -ngl 99 --parallel 1 --host 0.0.0.0 -fa on -ctk q8_0 -ctv q8_0"
    Write-Host "      model: Qwen3-8B (Q4_K_M, q8 KV cache)"
} else {
    $llamaModel = $qwen25
    $llamaArgs = "--port 8001 -c 8192 -ngl 99 --parallel 1 --host 0.0.0.0"
    Write-Host "      model: Qwen2.5-3B (fallback - Qwen3-8B GGUF not found)"
}
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd /c `"$llamaExe`" -m `"$llamaModel`" $llamaArgs 2>>`"$llamaLog`""
}
Write-Host "      launched rc=$($r.ReturnValue)"

Write-Host "[3/4] backend (:8000)..."
$uvOutLog = Join-Path $DataDir "uvicorn.out.log"
$uvErrLog = Join-Path $DataDir "uvicorn.err.log"
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd /c cd /d `"$BackendDir`" && `"$VenvPython`" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 1>>`"$uvOutLog`" 2>>`"$uvErrLog`""
}
Set-Content -Path $PidFile -Value $r.ProcessId
Write-Host "      launched rc=$($r.ReturnValue)"

Write-Host "[4/4] job worker..."
$wOutLog = Join-Path $DataDir "worker.out.log"
$wErrLog = Join-Path $DataDir "worker.err.log"
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd /c cd /d `"$BackendDir`" && `"$VenvPython`" `"$WorkerPy`" 1>>`"$wOutLog`" 2>>`"$wErrLog`""
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
