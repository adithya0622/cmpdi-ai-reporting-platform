@echo off
title CMPDI AI Reporting Platform - Startup
echo ======================================================================
echo   CMPDI / Coal India Limited AI Reporting Platform
echo   Ministry of Coal - Smart India Hackathon
echo ======================================================================
echo.

echo [1/4] Ensuring PostgreSQL database is active in WSL...
wsl -d Ubuntu -u root -- service postgresql start

echo.
echo [2/4] Starting Local LLM Inference Engine (GPU Accelerated)...
start "CMPDI LLM Server (Port 8001)" /min cmd /c "data\llm\llama-server.exe -m data\llm\qwen2.5-3b-instruct-q4_k_m.gguf --port 8001 -c 8192 -ngl 99 --parallel 1 --host 0.0.0.0"

echo.
echo [3/4] Starting CMPDI FastAPI Backend Server (Port 8000)...
start "CMPDI Backend (Port 8000)" /min cmd /c "cd backend && ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --host 0.0.0.0"

echo.
echo [4/4] Launching Web Interface...
timeout /t 3 /nobreak >nul
start http://localhost:8000

echo.
echo ======================================================================
echo   All services launched successfully!
echo   Web Platform: http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo   Default Login: admin / demo123
echo ======================================================================
echo.
pause
