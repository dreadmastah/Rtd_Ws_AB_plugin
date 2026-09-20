@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set JOURNAL=%BUILD%\leverage_margin_risk_journal.jsonl
set STATUS=%BUILD%\leverage_margin_risk_status.v1.json
set FIRST=%BUILD%\leverage_margin_risk_first.out
set RC=0

if not exist "%HOST%" exit /b 2
if not exist "%CLIENT%" exit /b 2
if not exist "%RECON%" exit /b 2

del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%FIRST%" >nul 2>nul

rem Phase A: effective leverage.
start "ASTU Effective Leverage Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-available-balance 1000 ^
  --synthetic-margin-balance 5 ^
  --synthetic-initial-margin 0 ^
  --synthetic-max-gross-notional 100000 ^
  --max-effective-leverage 2 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id LEV-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL LEVERAGE_FIRST
  set RC=3
  goto cleanup
)
"%CLIENT%" --case-id LEV-2 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL LEVERAGE_LIMIT
  set RC=4
  goto cleanup
)
python -c "import json,time; p=r'%STATUS%'; deadline=time.time()+5; last=None
while time.time()<deadline:
  try:
    last=json.load(open(p,encoding='utf-8'))
    if abs(float(last.get('maxEffectiveLeverage',0))-2.0)<1e-12 and last.get('maxMarginUtilization')==0 and last.get('activeExposureReservations')==1 and abs(float(last.get('reservedGrossNotional',0))-10.0)<1e-9 and last.get('orderRoutingEnabled') is False: print('EFFECTIVE_LEVERAGE_LIMIT=PASS'); raise SystemExit(0)
  except (OSError,ValueError,json.JSONDecodeError): pass
  time.sleep(0.1)
raise AssertionError(last)"
if errorlevel 1 (
  set RC=5
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul
del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul

rem Phase B: margin utilization with durable projected margin.
start "ASTU Margin Utilization Host 1" /b "%HOST%" ^
  --synthetic ^
  --synthetic-available-balance 1000 ^
  --synthetic-margin-balance 10 ^
  --synthetic-initial-margin 0 ^
  --synthetic-max-gross-notional 100000 ^
  --simulation-margin-reservation-rate 0.5 ^
  --max-margin-utilization 0.5 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id MARGIN-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED > "%FIRST%" 2>&1
if errorlevel 1 (
  type "%FIRST%"
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL MARGIN_FIRST
  set RC=6
  goto cleanup
)
type "%FIRST%"
for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%FIRST%"') do set ORDER_ID=%%A
for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulatedQuantity=" "%FIRST%"') do set ORDER_QTY=%%A
if "!ORDER_ID!"=="" set RC=7
if "!ORDER_QTY!"=="" set RC=7
if not !RC! EQU 0 goto cleanup

"%CLIENT%" --case-id MARGIN-2 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL MARGIN_LIMIT
  set RC=8
  goto cleanup
)
python -c "import json,time; p=r'%STATUS%'; deadline=time.time()+5; last=None
while time.time()<deadline:
  try:
    last=json.load(open(p,encoding='utf-8'))
    if abs(float(last.get('maxMarginUtilization',0))-0.5)<1e-12 and abs(float(last.get('simulationMarginReservationRate',0))-0.5)<1e-12 and abs(float(last.get('reservedAvailableBalance',0))-5.0)<1e-9: print('MARGIN_UTILIZATION_LIMIT=PASS'); raise SystemExit(0)
  except (OSError,ValueError,json.JSONDecodeError): pass
  time.sleep(0.1)
raise AssertionError(last)"
if errorlevel 1 (
  set RC=9
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Margin Utilization Host 2" /b "%HOST%" ^
  --synthetic ^
  --synthetic-available-balance 1000 ^
  --synthetic-margin-balance 10 ^
  --synthetic-initial-margin 0 ^
  --synthetic-max-gross-notional 100000 ^
  --simulation-margin-reservation-rate 0.5 ^
  --max-margin-utilization 0.5 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id MARGIN-3 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL MARGIN_RESTART
  set RC=10
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id LM-UNKNOWN --event MARK_UNKNOWN --cumulative-filled 0 --detail "leverage margin smoke unknown"
if errorlevel 1 set RC=11
if not !RC! EQU 0 goto cleanup
"%RECON%" --order-id "!ORDER_ID!" --event-id LM-WORKING --event WORKING --cumulative-filled 0 --detail "leverage margin smoke working"
if errorlevel 1 set RC=12
if not !RC! EQU 0 goto cleanup
"%RECON%" --order-id "!ORDER_ID!" --event-id LM-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!" --detail "leverage margin smoke filled"
if errorlevel 1 set RC=13
if not !RC! EQU 0 goto cleanup

"%CLIENT%" --case-id MARGIN-4 --symbol ETHUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL MARGIN_RELEASE_REUSE
  set RC=14
  goto cleanup
)

python -c "import json,time; p=r'%STATUS%'; deadline=time.time()+5; last=None
while time.time()<deadline:
  try:
    last=json.load(open(p,encoding='utf-8'))
    if last.get('exposureReservationReleaseCount')==1 and last.get('activeExposureReservations')==1 and abs(float(last.get('reservedAvailableBalance',0))-5.0)<1e-9 and last.get('orderRoutingEnabled') is False: print('MARGIN_UTILIZATION_RESTART_RELEASE=PASS'); raise SystemExit(0)
  except (OSError,ValueError,json.JSONDecodeError): pass
  time.sleep(0.1)
raise AssertionError(last)"
if errorlevel 1 set RC=15

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
if !RC! EQU 0 (
  echo LEVERAGE_MARGIN_RISK_SMOKE=PASS
  echo EFFECTIVE_LEVERAGE=PASS
  echo MARGIN_UTILIZATION=PASS
  echo MARGIN_RESTART=PASS
  echo TERMINAL_RELEASE=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo LEVERAGE_MARGIN_RISK_SMOKE=FAIL RC=!RC!
)
exit /b !RC!
