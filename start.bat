@echo off
chcp 65001 >nul
title Windroida
cd /d "%~dp0"
rem First run: makes a private ".venv" folder, installs everything the 3 servers need into it
rem (from the "wheels" folder = no internet needed; if wheels is empty it downloads from pypi.org over https).
rem Next runs: starts right away. Delete the ".venv" folder to redo it.
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY goto nopython

if exist ".venv\Scripts\python.exe" goto havevenv
echo.
echo   First run: preparing .venv ...  /  اولین اجرا: ساخت پوشه .venv
%PY% -m venv .venv
if errorlevel 1 goto novenv
:havevenv
set VPY=.venv\Scripts\python.exe
if exist ".venv\deps.ok" goto run
echo   Installing libraries (offline from "wheels" first) ...  /  نصب کتابخونه‌ها
dir /b wheels\*.whl >nul 2>nul
if not errorlevel 1 "%VPY%" -m pip install --disable-pip-version-check -q --no-index --find-links wheels -r requirements-all.txt && goto depsok
echo   wheels folder missing/incomplete - trying the internet ...  /  تلاش از اینترنت
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements-all.txt && goto depsok
echo.
echo   Could not install all libraries. The messenger still starts (some features limited).
echo   On a PC with internet run download_wheels.bat once, then copy this whole folder.
goto run
:depsok
echo ok> ".venv\deps.ok"
:run
"%VPY%" start.py %*
if errorlevel 1 pause
exit /b
:novenv
echo   Could not create .venv - using the normal Python instead.  /  با پایتون معمولی ادامه می‌دم
%PY% start.py %*
if errorlevel 1 pause
exit /b
:nopython
echo.
echo   Python is not installed.
echo   Download it from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" in the installer, then run start.bat again.
echo.
pause
