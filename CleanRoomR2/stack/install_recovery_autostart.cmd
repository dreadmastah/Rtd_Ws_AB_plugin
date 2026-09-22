@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "DBNAME=%~1"
if "%DBNAME%"=="" set "DBNAME=Data"
if not exist ".venv\Scripts\python.exe" (
  call install_wsrtd_stack.cmd
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" autostart_manager.py --install --dbname "%DBNAME%"
exit /b %errorlevel%
