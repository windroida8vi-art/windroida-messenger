@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Run this ONCE on a PC that has full internet. It saves every library of all 3 servers into "wheels"
rem for Windows 64-bit and Python 3.10 - 3.14. Then copy the WHOLE folder to any other PC (no internet needed there):
rem start.bat builds .venv from "wheels" by itself. (Python itself must be installed on that PC.)
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY set PY=python
if not exist wheels mkdir wheels
for %%V in (310 311 312 313 314) do (
  echo --- Python %%V
  %PY% -m pip download -q --only-binary=:all: --platform win_amd64 --python-version %%V --implementation cp -r requirements-all.txt -d wheels
)
rem pure-python packages (py3-none-any) and the current Python as a fallback
%PY% -m pip download -q -r requirements-all.txt -d wheels
echo.
echo Done. The "wheels" folder now has everything for offline install. / تموم شد
pause
