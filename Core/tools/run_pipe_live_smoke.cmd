@echo off
setlocal
set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%ROOT%\..\CleanRoomR2\stack\runtime\autotrader_status

if not "%~1"=="" set STATUS=%~1

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)

if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)

if not exist "%STATUS%\BTCUSDT.json" (
  echo ERROR: missing live status %STATUS%\BTCUSDT.json
  exit /b 3
)

start "ASTU Execution Live Status Host" /b "%HOST%" --status-dir "%STATUS%"
timeout /t 1 /nobreak >nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT
set RC=%ERRORLEVEL%

if %RC% EQU 0 (
  echo PIPE_LIVE_STATUS_SMOKE=PASS
) else (
  echo PIPE_LIVE_STATUS_SMOKE=FAIL RC=%RC%
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
exit /b %RC%
