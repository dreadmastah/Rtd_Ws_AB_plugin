@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set TRADE=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set JOURNAL=%BUILD%\reconciliation_pipe_journal.jsonl
set STATUS=%BUILD%\reconciliation_pipe_status.v1.json
set TRADE_OUT=%BUILD%\reconciliation_pipe_trade.out
set RC=0

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)
if not exist "%TRADE%" (
  echo ERROR: missing %TRADE%
  exit /b 2
)
if not exist "%RECON%" (
  echo ERROR: missing %RECON%
  exit /b 2
)

del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%TRADE_OUT%" >nul 2>nul

start "ASTU Reconciliation Pipe Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%TRADE%" > "%TRADE_OUT%" 2>&1
if errorlevel 1 (
  type "%TRADE_OUT%"
  echo RECONCILIATION_PIPE_SMOKE=FAIL SEED_REQUEST
  set RC=3
  goto cleanup
)
type "%TRADE_OUT%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%TRADE_OUT%"') do set ORDER_ID=%%A
if "!ORDER_ID!"=="" (
  echo RECONCILIATION_PIPE_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)

for /f "delims=" %%Q in ('python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; x=next(x for x in rows if x.get('eventType')=='SIMULATION_ORDER_INTENT'); print(format(float(x['quantity']),'.17g'))"') do set ORDER_QTY=%%Q
for /f "delims=" %%Q in ('python -c "q=float('!ORDER_QTY!'); print(format(q/2.0,'.17g'))"') do set HALF_QTY=%%Q

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-UNKNOWN --event MARK_UNKNOWN
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL MARK_UNKNOWN
  set RC=5
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-ACK --event ACKNOWLEDGED
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL ACKNOWLEDGED
  set RC=6
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-WORKING --event WORKING
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL WORKING
  set RC=7
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-PARTIAL --event PARTIAL_FILL --cumulative-filled "!HALF_QTY!"
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL PARTIAL_FILL
  set RC=8
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!"
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL FILLED
  set RC=9
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id PIPE-CANCEL-AFTER-FILL --event CANCELED --cumulative-filled "!ORDER_QTY!" --expect-rejected
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL TERMINAL_REJECTION
  set RC=10
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['trackedOrders']==1, o; assert o['orderTransitionCount']==9, o; assert o['reconciliationEventCount']==5, o; assert o['orderRoutingEnabled'] is False; print('RECONCILIATION_PIPE_LIVE_STATUS=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL LIVE_STATUS
  set RC=11
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; ev=[x for x in rows if x.get('eventType')=='SIMULATION_RECONCILIATION_EVENT']; assert [x['toState'] for x in ev]==['UNKNOWN_RECONCILE_REQUIRED','ACKNOWLEDGED','WORKING','PARTIAL','FILLED']; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('RECONCILIATION_PIPE_JOURNAL=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL JOURNAL
  set RC=12
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Reconciliation Pipe Recovery Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json,time; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['recoveredOrdersAtStartup']==1, o; assert o['trackedOrders']==1, o; assert o['orderTransitionCount']==9, o; assert o['recoveredReconciliationEventsAtStartup']==5, o; assert o['reconciliationEventCount']==5, o; assert o['orderRoutingEnabled'] is False; age=int(time.time()*1000)-int(o['generatedUnixMs']); assert 0<=age<5000, age; print('RECONCILIATION_PIPE_RESTART=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_PIPE_SMOKE=FAIL RESTART
  set RC=13
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo RECONCILIATION_PIPE_SMOKE=PASS
  echo FINAL_STATE=FILLED
  echo RECONCILIATION_EVENTS=5
  echo ORDER_TRANSITIONS=9
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo RECONCILIATION_PIPE_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
