@echo off
setlocal
set ROOT=%~dp0..
set REPO=%ROOT%\..
set BUILD=%REPO%\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%REPO%\CleanRoomR2\stack\runtime\autotrader_status
set RISK=%BUILD%\instrument_filter_risk.v1.json
set RULES=%BUILD%\instrument_constraints
set JOURNAL=%BUILD%\instrument_filter_journal.jsonl
set OUT=%BUILD%\instrument_filter_smoke.out
set BRIDGE=%REPO%\CleanRoomR2\stack\identity_bridge.py
set GATEWAY=%ROOT%\account\binance_usdm_readonly_gateway.py
set RISK_FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_account_v3.json
set RULES_PUBLISHER=%ROOT%\instrument\binance_usdm_instrument_rules.py
set RULES_FIXTURE=%ROOT%\instrument\tests\fixtures\binance_usdm_exchange_info_btc.json

python "%BRIDGE%" --once
if errorlevel 1 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL STATUS_REFRESH
  exit /b 3
)

python "%GATEWAY%" --once --fixture "%RISK_FIXTURE%" --output "%RISK%"
if errorlevel 1 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL RISK_REFRESH
  exit /b 4
)

python "%RULES_PUBLISHER%" --once --fixture "%RULES_FIXTURE%" --output-dir "%RULES%" --symbols BTCUSDT
if errorlevel 1 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL RULES_REFRESH
  exit /b 5
)

del /q "%JOURNAL%" >nul 2>nul
del /q "%OUT%" >nul 2>nul

start "ASTU Instrument Filter Host" /b "%HOST%" ^
  --status-dir "%STATUS%" ^
  --risk-status-file "%RISK%" ^
  --instrument-status-dir "%RULES%" ^
  --max-instrument-status-age-ms 5000 ^
  --journal "%JOURNAL%"

ping -n 2 127.0.0.1 >nul

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id instrument-filter --trigger-price 100 --expect ORDER_ROUTING_DISABLED > "%OUT%" 2>&1
set RC=%ERRORLEVEL%
type "%OUT%"

if not %RC% EQU 0 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL RC=%RC%
  taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
  exit /b %RC%
)

findstr /C:"simulatedQuantity=0.102" "%OUT%" >nul
if errorlevel 1 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL QUANTITY
  taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
  exit /b 6
)

findstr /C:"simulatedNotional=10.2" "%OUT%" >nul
if errorlevel 1 (
  echo INSTRUMENT_FILTER_PIPE_SMOKE=FAIL NOTIONAL
  taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
  exit /b 7
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

echo INSTRUMENT_FILTER_PIPE_SMOKE=PASS
echo ORDER_ROUTING_ENABLED=false
exit /b 0
