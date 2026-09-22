@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo WSRTD_STACK_STATUS=NO_VENV
  exit /b 1
)
".venv\Scripts\python.exe" stack_launcher.py --stop %* --stop-source cmd-wrapper
