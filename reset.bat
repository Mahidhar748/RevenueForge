@echo off
REM Deletes ALL local data: companies, users, uploaded files, RFPs and generated documents.
REM Your backend\.env (API keys) is kept.
cd /d %~dp0
set /p ok=This permanently deletes all RevenueForge data on this computer. Type YES to continue: 
if /I not "%ok%"=="YES" exit /b 0

echo Stopping RevenueForge if it is running...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|uvicorn|node' -and ($_.CommandLine -like '*revenueforge*' -or $_.CommandLine -like '*multiprocessing*spawn_main*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
taskkill /FI "WINDOWTITLE eq RevenueForge API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RevenueForge Web*" /T /F >nul 2>&1
timeout /t 2 >nul

if exist backend\data rmdir /s /q backend\data
if exist backend\data (
  echo.
  echo Could not delete backend\data: a file is still in use.
  echo Close every RevenueForge window and terminal, then run reset.bat again.
  exit /b 1
)
echo All data deleted. Run start.bat and register a new company.
