@echo off
setlocal
set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%ROOT%\..\CleanRoomR2\stack\runtime\autotrader_status
set RISK=%ROOT%\runtime\account_risk_status.v1.json
set JOURNAL=%BUILD%\reconciliation_restart_journal.jsonl
set GATEWAY=%ROOT%\account\binance_usdm_readonly_gateway.py
set FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_account_v3.json
set BRIDGE=%ROOT%\..\CleanRoomR2\stack\identity_bridge.py

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

del /q "%JOURNAL%" >nul 2>nul

python "%BRIDGE%" --once
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL STATUS_REFRESH_CASE1
  exit /b 3
)

python "%GATEWAY%" --once --fixture "%FIXTURE%" --output "%RISK%"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL INITIAL_RISK
  exit /b 4
)

start "ASTU Reconciliation Case 1" /b "%HOST%" --status-dir "%STATUS%" --risk-status-file "%RISK%" --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id 1 --expect ORDER_ROUTING_DISABLED
set CASE1=%ERRORLEVEL%
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
if not %CASE1% EQU 0 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL CASE1=%CASE1%
  exit /b %CASE1%
)

del /q "%RISK%" >nul 2>nul
python "%BRIDGE%" --once
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL STATUS_REFRESH_CASE2
  exit /b 3
)
ping -n 2 127.0.0.1 >nul
start "ASTU Reconciliation Case 2" /b "%HOST%" --status-dir "%STATUS%" --risk-status-file "%RISK%" --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id 2 --expect ACCOUNT_NOT_RECONCILED
set CASE2=%ERRORLEVEL%
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
if not %CASE2% EQU 0 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL CASE2=%CASE2%
  exit /b %CASE2%
)

python "%GATEWAY%" --once --fixture "%FIXTURE%" --output "%RISK%"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL RESTORE_RISK
  exit /b 5
)
python "%BRIDGE%" --once
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL STATUS_REFRESH_CASE3
  exit /b 3
)

ping -n 2 127.0.0.1 >nul
start "ASTU Reconciliation Case 3" /b "%HOST%" --status-dir "%STATUS%" --risk-status-file "%RISK%" --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id 3 --expect ORDER_ROUTING_DISABLED
set CASE3=%ERRORLEVEL%
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
if not %CASE3% EQU 0 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL CASE3=%CASE3%
  exit /b %CASE3%
)

findstr /C:"ACCOUNT_NOT_RECONCILED" "%JOURNAL%" >nul
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL JOURNAL_MISSING_BLOCK
  exit /b 6
)

echo RECONCILIATION_RESTART_SMOKE=PASS
echo CASE1_RECONCILED=ORDER_ROUTING_DISABLED
echo CASE2_RISK_MISSING=ACCOUNT_NOT_RECONCILED
echo CASE3_RECONCILED_RESTORED=ORDER_ROUTING_DISABLED
exit /b 0
