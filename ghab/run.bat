@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Ghab - port 8084
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)
if not exist venv (
  echo Creating virtual environment...
  python -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Package install failed. Check your internet connection.
  pause
  exit /b 1
)
rem --- optional settings (one value per file, first line) ---
if exist public_host.txt set /p GHAB_PUBLIC=<public_host.txt
if exist admin_password.txt set /p ADMIN_PASSWORD=<admin_password.txt
if exist plain_mode.txt set GHAB_PLAIN=1
if exist port.txt set /p GHAB_PORT=<port.txt
set PYTHONIOENCODING=utf-8
:run
python app.py
echo.
echo Server stopped. Restarting in 3 seconds... (close this window to quit)
timeout /t 3 /nobreak >nul
goto run
