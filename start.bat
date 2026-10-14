@echo off
REM Starts the API (port 8000) and the web app (port 5173), then opens the browser.
cd /d %~dp0
start "RevenueForge API" cmd /k "cd backend && .venv\Scripts\activate.bat && uvicorn app.main:app --port 8000 --reload"
start "RevenueForge Web" cmd /k "cd frontend && npm run dev"
timeout /t 5 >nul
start http://localhost:5173
