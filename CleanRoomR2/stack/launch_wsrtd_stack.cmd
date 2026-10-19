@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "runtime\maintenance_pause" del /q "runtime\maintenance_pause" >nul 2>nul
set "DBNAME=%~1"
if "%DBNAME%"=="" set "DBNAME=Data"

if not exist ".venv\Scripts\python.exe" (
  call install_wsrtd_stack.cmd
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import aiohttp,websockets" >nul 2>nul
if errorlevel 1 (
  call install_wsrtd_stack.cmd
  if errorlevel 1 exit /b 1
)

echo.
echo WSRTD headless stack launch requested for AmiBroker DB name "%DBNAME%".
echo Bootstrap list: bootstrap_symbols.tls
echo Relay: ws://127.0.0.1:10101
echo Runtime: background/no-console
echo.

".venv\Scripts\python.exe" stack_launcher.py --ensure-running --dbname "%DBNAME%"
if errorlevel 1 (
  echo WSRTD_HEADLESS_LAUNCH=FAIL
  exit /b 1
)
timeout /t 3 /nobreak >nul
".venv\Scripts\python.exe" stack_launcher.py --status
if errorlevel 1 (
  echo WSRTD_HEADLESS_LAUNCH=FAIL_STATUS
  exit /b 1
)
echo WSRTD_HEADLESS_LAUNCH=PASS
echo To stop the background stack, run stop_wsrtd_stack.cmd
exit /b 0
