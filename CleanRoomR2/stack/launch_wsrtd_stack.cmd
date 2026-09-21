@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "runtime\maintenance_pause" del /q "runtime\maintenance_pause" >nul 2>nul
set "DBNAME=%~1"
if "%DBNAME%"=="" set "DBNAME=Data"
set "PORT=%~2"
if "%PORT%"=="" set "PORT=10101"
set "WSRTD_RELAY_HOST=127.0.0.1"
set "WSRTD_RELAY_PORT=%PORT%"
set "WSRTD_RELAY_URI=ws://127.0.0.1:%PORT%/sender"

if not exist ".venv\Scripts\python.exe" (
  call install_wsrtd_stack.cmd
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import aiohttp,websockets" >nul 2>nul
if errorlevel 1 (
  call install_wsrtd_stack.cmd
  if errorlevel 1 exit /b 1
)

call configure_plugin_registry.cmd "%DBNAME%" "%PORT%"
if errorlevel 1 exit /b 1

echo.
echo WSRTD stack starting for AmiBroker DB name "%DBNAME%".
echo Bootstrap list: bootstrap_symbols.tls
echo Relay: ws://127.0.0.1:%PORT%
echo Press Ctrl+C in this window to stop relay and Binance sender.
echo.
".venv\Scripts\python.exe" -u stack_launcher.py --dbname "%DBNAME%" --relay-port "%PORT%"
exit /b %errorlevel%
