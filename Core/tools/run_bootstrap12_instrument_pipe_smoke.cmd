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
set RISK=%BUILD%\bootstrap12_instrument_risk.v1.json
set GATEWAY=%ROOT%\account\binance_usdm_readonly_gateway.py
set RISK_FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_account_v3.json
set RULES=%BUILD%\bootstrap12_instrument_constraints
set RULES_PUBLISHER=%ROOT%\instrument\binance_usdm_instrument_rules.py
set RULES_FIXTURE=%ROOT%\instrument\tests\fixtures\binance_usdm_exchange_info_bootstrap12.json
set JOURNAL=%BUILD%\bootstrap12_instrument_journal.jsonl
set RC=0

python "%BRIDGE%" --once
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL STATUS_REFRESH
  exit /b 3
)

rem This smoke exercises all 12 BUY simulations. Keep the unrelated
rem projected open-position cap above the bootstrap universe size.
python "%GATEWAY%" --once --fixture "%RISK_FIXTURE%" --output "%RISK%" ^
  --max-open-positions 64
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL RISK_REFRESH
  exit /b 4
)

rmdir /s /q "%RULES%" >nul 2>nul
python "%RULES_PUBLISHER%" --once ^
  --fixture "%RULES_FIXTURE%" ^
  --output-dir "%RULES%" ^
  --symbols-file "%SYMBOLS%"
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL RULES_REFRESH
  exit /b 5
)

del /q "%JOURNAL%" >nul 2>nul
start "ASTU Bootstrap12 Instrument Host" /b "%HOST%" ^
  --status-dir "%STATUS%" ^
  --max-status-age-ms 60000 ^
  --risk-status-file "%RISK%" ^
  --max-risk-status-age-ms 60000 ^
  --instrument-status-dir "%RULES%" ^
  --max-instrument-status-age-ms 60000 ^
  --journal "%JOURNAL%"

ping -n 2 127.0.0.1 >nul

set COUNT=0
for /f "usebackq tokens=* delims=" %%S in ("%SYMBOLS%") do (
  if not "%%S"=="" (
    set /a COUNT+=1
    "%CLIENT%" --status-dir "%STATUS%" --symbol %%S --case-id bootstrap12-%%S --trigger-price 1 --expect ORDER_ROUTING_DISABLED
    if errorlevel 1 (
      echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL SYMBOL=%%S
      set RC=6
      goto cleanup
    )
  )
)

if not "!COUNT!"=="12" (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL SYMBOL_COUNT=!COUNT!
  set RC=7
  goto cleanup
)

del /q "%RULES%\ETHUSDT.json" >nul 2>nul
"%CLIENT%" --status-dir "%STATUS%" --symbol ETHUSDT --case-id bootstrap12-missing-ETH --trigger-price 1 --expect INSTRUMENT_UNAVAILABLE
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL MISSING_FILTER_DID_NOT_FAIL_CLOSED
  set RC=8
  goto cleanup
)

python "%RULES_PUBLISHER%" --once ^
  --fixture "%RULES_FIXTURE%" ^
  --output-dir "%RULES%" ^
  --symbols-file "%SYMBOLS%"
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL FILTER_RECOVERY_REFRESH
  set RC=9
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol ETHUSDT --case-id bootstrap12-recovered-ETH --trigger-price 1 --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL FILTER_RECOVERY_REQUEST
  set RC=10
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=PASS
  echo BOOTSTRAP_SYMBOLS_EXERCISED=!COUNT!
  echo MISSING_FILTER_FAIL_CLOSED=PASS
  echo FILTER_RECOVERY=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo BOOTSTRAP12_INSTRUMENT_PIPE_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
