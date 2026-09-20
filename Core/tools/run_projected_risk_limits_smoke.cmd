@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set JOURNAL=%BUILD%\projected_risk_limits_journal.jsonl
set STATUS=%BUILD%\projected_risk_limits_status.v1.json
set FIRST=%BUILD%\projected_risk_limits_first.out
set RC=0

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)
if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)
if not exist "%RECON%" (
  echo ERROR: missing %RECON%
  exit /b 2
)

del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%FIRST%" >nul 2>nul

rem Phase A: pending entry/scale-in reservation count.
start "ASTU Projected Risk Pending Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 1 ^
  --max-symbol-notional 0 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id PENDING-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED > "%FIRST%" 2>&1
if errorlevel 1 (
  type "%FIRST%"
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_FIRST_ACCEPT
  set RC=3
  goto cleanup
)
type "%FIRST%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%FIRST%"') do set ORDER_ID=%%A
for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulatedQuantity=" "%FIRST%"') do set ORDER_QTY=%%A
if "!ORDER_ID!"=="" (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)
if "!ORDER_QTY!"=="" (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL ORDER_QTY_MISSING
  set RC=5
  goto cleanup
)

"%CLIENT%" --case-id PENDING-2 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_LIMIT_NOT_ENFORCED
  set RC=6
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; o=json.load(open(r'%STATUS%',encoding='utf-8')); assert o['maxPendingEntryScaleInReservations']==1, o; assert o['maxSymbolNotional']==0, o; assert o['activeExposureReservations']==1, o; assert o['reservedPositionSlots']==1, o; assert o['orderRoutingEnabled'] is False; print('PROJECTED_PENDING_LIMIT=PASS')"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_STATUS
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Projected Risk Pending Restart Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 1 ^
  --max-symbol-notional 0 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id PENDING-3 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_RESTART_NOT_ENFORCED
  set RC=8
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-UNKNOWN --event MARK_UNKNOWN --cumulative-filled 0 --detail "pending limit release unknown"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_MARK_UNKNOWN
  set RC=9
  goto cleanup
)
"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-WORKING --event WORKING --cumulative-filled 0 --detail "pending limit release working"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_WORKING
  set RC=10
  goto cleanup
)
"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!" --detail "pending limit release filled"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_FILLED
  set RC=11
  goto cleanup
)

"%CLIENT%" --case-id PENDING-4 --symbol ETHUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_HEADROOM_NOT_RESTORED
  set RC=12
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Phase B: per-symbol projected notional.
del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul

start "ASTU Projected Risk Symbol Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 0 ^
  --max-symbol-notional 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id SYMBOL-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_FIRST_ACCEPT
  set RC=13
  goto cleanup
)

"%CLIENT%" --case-id SYMBOL-2 --symbol BTCUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_LIMIT_NOT_ENFORCED
  set RC=14
  goto cleanup
)

"%CLIENT%" --case-id SYMBOL-3 --symbol ETHUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_ISOLATION
  set RC=15
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; o=json.load(open(r'%STATUS%',encoding='utf-8')); assert o['maxPendingEntryScaleInReservations']==0, o; assert abs(float(o['maxSymbolNotional'])-10.0)<1e-12, o; assert o['activeExposureReservations']==2, o; assert abs(float(o['reservedGrossNotional'])-20.0)<1e-9, o; assert o['reservedPositionSlots']==2, o; assert o['orderRoutingEnabled'] is False; print('PROJECTED_SYMBOL_LIMIT=PASS')"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_STATUS
  set RC=16
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; creates=[x for x in rows if x.get('eventType')=='EXPOSURE_RESERVATION_CREATED']; assert len(creates)==2, len(creates); assert {x['symbol'] for x in creates}=={'BTCUSDT','ETHUSDT'}; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('PROJECTED_RISK_LIMITS_JOURNAL=PASS')"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL JOURNAL
  set RC=17
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo PROJECTED_RISK_LIMITS_SMOKE=PASS
  echo PENDING_RESERVATION_LIMIT=PASS
  echo PENDING_LIMIT_RESTART=PASS
  echo TERMINAL_RELEASE_RESTORES_SLOT=PASS
  echo PER_SYMBOL_PROJECTED_NOTIONAL=PASS
  echo SYMBOL_ISOLATION=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
