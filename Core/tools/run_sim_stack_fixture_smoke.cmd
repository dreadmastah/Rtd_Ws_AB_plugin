@echo off
setlocal
set ROOT=%~dp0..
set REPO=%ROOT%\..
set BUILD=%REPO%\build\core
set LAUNCHER=%ROOT%\stack\autotrader_sim_launcher.py
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%REPO%\CleanRoomR2\stack\runtime\autotrader_status
set JOURNAL=%BUILD%\sim_stack_fixture_journal.jsonl

if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)
if not exist "%STATUS%\BTCUSDT.json" (
  echo ERROR: missing %STATUS%\BTCUSDT.json
  exit /b 3
)

python "%REPO%\CleanRoomR2\stack\identity_bridge.py" --once
if errorlevel 1 (
  echo SIM_STACK_FIXTURE_SMOKE=FAIL STATUS_REFRESH
  exit /b 3
)

del /q "%JOURNAL%" >nul 2>nul
start "ASTU Simulation Stack Fixture" /b python "%LAUNCHER%" --risk-mode fixture --journal "%JOURNAL%" --status-dir "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id stack-fixture --expect ORDER_ROUTING_DISABLED
set RC=%ERRORLEVEL%

python "%LAUNCHER%" --stop >nul 2>nul

if %RC% EQU 0 (
  echo SIM_STACK_FIXTURE_SMOKE=PASS
) else (
  echo SIM_STACK_FIXTURE_SMOKE=FAIL RC=%RC%
)

exit /b %RC%
