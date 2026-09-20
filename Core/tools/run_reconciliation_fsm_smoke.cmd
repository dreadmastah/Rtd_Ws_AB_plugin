@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_sim_reconcile.exe
set JOURNAL=%BUILD%\reconciliation_restart_journal.jsonl
set STATUS=%BUILD%\reconciliation_restart_status.v1.json
set REQUEST_OUT=%BUILD%\reconciliation_request.out
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
del /q "%REQUEST_OUT%" >nul 2>nul

start "ASTU Reconciliation Seed Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" > "%REQUEST_OUT%" 2>&1
if errorlevel 1 (
  type "%REQUEST_OUT%"
  echo RECONCILIATION_RESTART_SMOKE=FAIL SEED_REQUEST
  set RC=3
  goto cleanup
)
type "%REQUEST_OUT%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%REQUEST_OUT%"') do set ORDER_ID=%%A
if "!ORDER_ID!"=="" (
  echo RECONCILIATION_RESTART_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

for /f "delims=" %%Q in ('python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; x=next(x for x in rows if x.get('eventType')=='SIMULATION_ORDER_INTENT'); print(format(float(x['quantity']),'.17g'))"') do set ORDER_QTY=%%Q
for /f "delims=" %%Q in ('python -c "q=float('!ORDER_QTY!'); print(format(q/2.0,'.17g'))"') do set HALF_QTY=%%Q

if "!ORDER_QTY!"=="" (
  echo RECONCILIATION_RESTART_SMOKE=FAIL ORDER_QUANTITY_MISSING
  set RC=5
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-UNKNOWN --event MARK_UNKNOWN --detail "simulated unknown state"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL MARK_UNKNOWN
  set RC=6
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-ACK --event ACKNOWLEDGED --detail "simulated authoritative acknowledgement"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL ACKNOWLEDGED
  set RC=7
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-WORKING --event WORKING --detail "simulated authoritative working"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL WORKING
  set RC=8
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-PARTIAL --event PARTIAL_FILL --cumulative-filled "!HALF_QTY!" --detail "simulated partial fill"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL PARTIAL_FILL
  set RC=9
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!" --detail "simulated full fill"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL FILLED
  set RC=10
  goto cleanup
)

"%RECON%" --journal "%JOURNAL%" --order-id "!ORDER_ID!" --event-id EV-CANCEL-AFTER-FILL --event CANCELED --cumulative-filled "!ORDER_QTY!" --detail "invalid terminal mutation"
if not errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL TERMINAL_MUTATION_ACCEPTED
  set RC=11
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; ev=[x for x in rows if x.get('eventType')=='SIMULATION_RECONCILIATION_EVENT']; assert len(ev)==5, len(ev); assert [x['toState'] for x in ev]==['UNKNOWN_RECONCILE_REQUIRED','ACKNOWLEDGED','WORKING','PARTIAL','FILLED']; assert [x['reconciliationSequence'] for x in ev]==[1,2,3,4,5]; assert ev[-1]['cumulativeFilledQuantity']==ev[-1]['orderQuantity']; assert all(x['simulationOnly'] is True and x['exchangeSubmissionAttempted'] is False for x in ev); print('RECONCILIATION_JOURNAL_CHAIN=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL JOURNAL_CHAIN
  set RC=12
  goto cleanup
)

start "ASTU Reconciliation Recovery Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json,time; o=json.load(open(r'%STATUS%',encoding='utf-8')); assert o['lifecycleState']=='READY'; assert o['orderRoutingEnabled'] is False; assert o['recoveredOrdersAtStartup']==1, o; assert o['trackedOrders']==1, o; assert o['orderTransitionCount']==9, o; assert o['recoveredReconciliationEventsAtStartup']==5, o; assert o['reconciliationEventCount']==5, o; age=int(time.time()*1000)-int(o['generatedUnixMs']); assert 0<=age<5000, age; print('RECONCILIATION_RECOVERY_STATUS=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL RECOVERY_STATUS
  set RC=13
  goto cleanup
)

"%CLIENT%" --expect-duplicate >nul 2>&1
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL DUPLICATE_GUARD_AFTER_RESTART
  set RC=14
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('RECONCILIATION_NO_SUBMISSION=PASS')"
if errorlevel 1 (
  echo RECONCILIATION_RESTART_SMOKE=FAIL SUBMISSION_INVARIANT
  set RC=15
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo RECONCILIATION_RESTART_SMOKE=PASS
  echo SIMULATION_ORDER_ID=!ORDER_ID!
  echo FINAL_STATE=FILLED
  echo RECONCILIATION_EVENTS=5
  echo ORDER_TRANSITIONS=9
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo RECONCILIATION_RESTART_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
