# Local dev deploy: WSL Postgres + backend + worker.
# One-time prerequisites: scripts/wsl_pg_setup.sh installs PG16+pgvector in WSL Ubuntu.
# backend/.env points at postgresql+pg8000://cmpdi:cmpdi@localhost:5432/cmpdi

Write-Output "[1/3] Postgres (WSL)..."
wsl -d Ubuntu -u root -- bash /mnt/d/PS2/scripts/wsl_pg_setup.sh

Write-Output "[2/3] Backend on :8000..."
$backend = Start-Process -FilePath "D:\PS2\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--port","8000" -WorkingDirectory "D:\PS2\backend" -PassThru -WindowStyle Hidden
$backend.Id | Set-Content "D:\PS2\backend.pid"

Write-Output "[3/3] Worker..."
Start-Process -FilePath "D:\PS2\.venv\Scripts\python.exe" -ArgumentList "D:\PS2\scripts\worker.py","--poll","3" -WorkingDirectory "D:\PS2\backend" -WindowStyle Hidden

Start-Sleep -Seconds 8
try {
    $login = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -Body '{"username":"admin","password":"demo123"}' -ContentType "application/json"
    $h = @{ "X-API-Token" = $login.token }
    $health = Invoke-RestMethod -Uri "http://localhost:8000/query/health" -Headers $h
    Write-Output ("up: db=" + $health.db + " llm=" + $health.llm + " | UI: http://localhost:8000 | login admin/demo123")
} catch {
    Write-Output "check failed - backend may still be starting; open http://localhost:8000"
}
