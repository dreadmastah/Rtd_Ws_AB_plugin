@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set REPO=%ROOT%\..
set BUILD=%REPO%\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%REPO%\CleanRoomR2\stack\runtime\autotrader_status
set SYMBOLS=%REPO%\CleanRoomR2\stack\bootstrap_symbols.tls
set BRIDGE=%REPO%\CleanRoomR2\stack\identity_bridge.py
set GATEWAY=%ROOT%\account\binance_usdm_readonly_gateway.py
set ACCOUNT_FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_account_v3.json
set RISK=%BUILD%\position_scale_risk.v1.json
set POSITIONS=%BUILD%\position_scale_status
set RULES=%BUILD%\position_scale_instrument_constraints
set RULES_PUBLISHER=%ROOT%\instrument\binance_usdm_instrument_rules.py
set RULES_FIXTURE=%ROOT%\instrument\tests\fixtures\binance_usdm_exchange_info_bootstrap12.json
set JOURNAL=%BUILD%\position_scale_journal.jsonl
set OUT=%BUILD%\position_scale.out
set RC=0

python "%BRIDGE%" --once
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL STATUS_REFRESH
  exit /b 3
)

rmdir /s /q "%POSITIONS%" >nul 2>nul
python "%GATEWAY%" --once ^
  --fixture "%ACCOUNT_FIXTURE%" ^
  --output "%RISK%" ^
  --positions-output-dir "%POSITIONS%" ^
  --symbols-file "%SYMBOLS%"
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL ACCOUNT_RECONCILIATION
  exit /b 4
)

rmdir /s /q "%RULES%" >nul 2>nul
python "%RULES_PUBLISHER%" --once ^
  --fixture "%RULES_FIXTURE%" ^
  --output-dir "%RULES%" ^
  --symbols-file "%SYMBOLS%"
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL RULES_REFRESH
  exit /b 5
)

del /q "%JOURNAL%" >nul 2>nul
start "ASTU Position Scale Host" /b "%HOST%" ^
  --status-dir "%STATUS%" ^
  --max-status-age-ms 60000 ^
  --risk-status-file "%RISK%" ^
  --max-risk-status-age-ms 60000 ^
  --position-status-dir "%POSITIONS%" ^
  --max-position-status-age-ms 60000 ^
  --instrument-status-dir "%RULES%" ^
  --max-instrument-status-age-ms 60000 ^
  --journal "%JOURNAL%"

ping -n 2 127.0.0.1 >nul

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id pos-scale-in-long --action SCALE_IN --side LONG --trigger-price 1000 --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL SCALE_IN_LONG
  set RC=6
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id pos-scale-out-long --action SCALE_OUT --side LONG --trigger-price 1000 --expect ORDER_ROUTING_DISABLED > "%OUT%" 2>&1
if errorlevel 1 (
  type "%OUT%"
  echo POSITION_SCALE_PIPE_SMOKE=FAIL SCALE_OUT_LONG
  set RC=7
  goto cleanup
)
type "%OUT%"
findstr /C:"simulatedQuantity=0.01" "%OUT%" >nul
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL SCALE_OUT_CAP
  set RC=8
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id pos-side-conflict --action SCALE_IN --side SHORT --trigger-price 1000 --expect POSITION_CONFLICT
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL SIDE_CONFLICT
  set RC=9
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol ETHUSDT --case-id pos-flat-conflict --action SCALE_IN --side LONG --trigger-price 1000 --expect POSITION_CONFLICT
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL FLAT_CONFLICT
  set RC=10
  goto cleanup
)

del /q "%POSITIONS%\BTCUSDT.json" >nul 2>nul
"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id pos-missing --action SCALE_IN --side LONG --trigger-price 1000 --expect POSITION_UNAVAILABLE
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL MISSING_POSITION
  set RC=11
  goto cleanup
)

python "%GATEWAY%" --once ^
  --fixture "%ACCOUNT_FIXTURE%" ^
  --output "%RISK%" ^
  --positions-output-dir "%POSITIONS%" ^
  --symbols-file "%SYMBOLS%"
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL POSITION_RECOVERY_REFRESH
  set RC=12
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id pos-recovered --action SCALE_IN --side LONG --trigger-price 1000 --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL POSITION_RECOVERY
  set RC=13
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo POSITION_SCALE_PIPE_SMOKE=PASS
  echo SCALE_IN_LONG=PASS
  echo SCALE_OUT_CAP=PASS
  echo SIDE_CONFLICT_FAIL_CLOSED=PASS
  echo FLAT_POSITION_FAIL_CLOSED=PASS
  echo MISSING_POSITION_FAIL_CLOSED=PASS
  echo POSITION_RECOVERY=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo POSITION_SCALE_PIPE_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
