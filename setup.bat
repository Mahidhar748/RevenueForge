@echo off
REM One-time setup on Windows: creates a Python virtual env, installs packages.
cd /d %~dp0
echo [1/3] Creating Python virtual environment...
python -m venv backend\.venv || goto :err
call backend\.venv\Scripts\activate.bat
echo [2/3] Installing backend packages...
pip install -r backend\requirements.txt || goto :err
echo [3/3] Installing frontend packages...
cd frontend
call npm install || goto :err
cd ..
echo.
echo Setup complete. Run start.bat, then create your company workspace in the browser.
goto :eof
:err
echo Setup failed. See the message above.
exit /b 1
