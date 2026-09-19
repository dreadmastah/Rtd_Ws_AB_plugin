@echo off
setlocal

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CALLER=%BUILD%\Release\astu_trade_amibroker_call_smoke.exe
set DLL=%BUILD%\Release\AstuTrade.dll
set STATUS=%ROOT%\..\CleanRoomR2\stack\runtime\autotrader_status
set RISK=%ROOT%\runtime\account_risk_status.v1.json
set JOURNAL=%BUILD%\amibroker_trade_e2e_journal.jsonl

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)
if not exist "%CALLER%" (
  echo ERROR: missing %CALLER%
  exit /b 2
)
if not exist "%DLL%" (
  echo ERROR: missing %DLL%
  exit /b 2
)
if not exist "%STATUS%\BTCUSDT.json" (
  echo ERROR: missing %STATUS%\BTCUSDT.json
  exit /b 3
)
if not exist "%RISK%" (
  echo ERROR: missing %RISK%
  exit /b 4
)

del /q "%JOURNAL%" >nul 2>nul

start "ASTU AmiBroker Trade E2E Host" /b "%HOST%" --status-dir "%STATUS%" --risk-status-file "%RISK%" --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul

"%CALLER%" "%DLL%" "%STATUS%"
set RC=%ERRORLEVEL%

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if %RC% EQU 0 (
  echo ASTU_TRADE_DLL_E2E_SMOKE=PASS
) else (
  echo ASTU_TRADE_DLL_E2E_SMOKE=FAIL RC=%RC%
)

exit /b %RC%
