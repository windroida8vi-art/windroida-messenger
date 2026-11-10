@echo off
cd /d "%~dp0"
set PY=
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
if not defined PY (
  where python >nul 2>nul
  if %errorlevel%==0 set PY=python
)
if not defined PY goto nopython
if not exist venv\Scripts\activate.bat %PY% -m venv venv
if not exist venv\Scripts\activate.bat goto fail
call venv\Scripts\activate.bat
if exist wheels goto offline
pip install -r requirements.txt
if errorlevel 1 goto pipfail
goto installed
:offline
pip install --no-index --find-links wheels -r requirements.txt
if errorlevel 1 goto pipfail
:installed
python manage.py has-admin
if errorlevel 1 python manage.py create-admin
python wsgi.py
pause
exit /b 0
:nopython
echo Python 3.12 or newer was not found. Install it from python.org and tick "Add Python to PATH", then run this file again.
pause
exit /b 1
:pipfail
echo Package install failed. If you have no access to PyPI, see README section 2: put a "wheels" folder next to this file.
pause
exit /b 1
:fail
echo Could not create the virtual environment.
pause
exit /b 1
