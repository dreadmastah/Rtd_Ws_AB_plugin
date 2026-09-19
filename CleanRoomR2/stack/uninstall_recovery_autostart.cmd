@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo WSRTD_AUTOSTART=FAIL_VENV_MISSING
  exit /b 1
)
".venv\Scripts\python.exe" autostart_manager.py --uninstall
exit /b %errorlevel%
