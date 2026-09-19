@echo off
setlocal
set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%ROOT%\..\CleanRoomR2\stack\runtime\autotrader_status
set JOURNAL=%BUILD%\pipe_live_smoke_execution_journal.jsonl
set RISK=%ROOT%\runtime\account_risk_status.v1.json

if not "%~1"=="" set STATUS=%~1
if not "%~2"=="" set RISK=%~2

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

if not exist "%RISK%" (
  echo ERROR: missing risk status %RISK%
  exit /b 4
)

del /q "%JOURNAL%" >nul 2>nul
start "ASTU Execution Live Status Host" /b "%HOST%" --status-dir "%STATUS%" --risk-status-file "%RISK%" --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT
set RC=%ERRORLEVEL%

if %RC% EQU 0 (
  echo PIPE_LIVE_STATUS_SMOKE=PASS
) else (
  echo PIPE_LIVE_STATUS_SMOKE=FAIL RC=%RC%
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
exit /b %RC%
