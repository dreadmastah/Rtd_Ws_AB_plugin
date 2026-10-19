@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [WSRTD] Installing Python environment...
if exist ".venv\Scripts\python.exe" goto :install

where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -m venv .venv >nul 2>nul
  if exist ".venv\Scripts\python.exe" goto :install
  py -3 -m venv .venv
  if exist ".venv\Scripts\python.exe" goto :install
)
where python >nul 2>nul
if errorlevel 1 (
  echo WSRTD_INSTALL=FAIL_NO_PYTHON
  echo Install Python 3.12 or newer, then rerun this script.
  exit /b 1
)
python -m venv .venv

:install
if not exist ".venv\Scripts\python.exe" (
  echo WSRTD_INSTALL=FAIL_VENV
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "import aiohttp,websockets; print('WSRTD_DEPENDENCIES=PASS')"
if errorlevel 1 exit /b 1
echo WSRTD_INSTALL=PASS
exit /b 0
