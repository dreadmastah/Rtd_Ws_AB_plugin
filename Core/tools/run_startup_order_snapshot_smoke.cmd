@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set TRADE=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set SOURCE=%ROOT%\order_state\simulated_order_state_source.py
set JOURNAL=%BUILD%\startup_snapshot_journal.jsonl
set STATUS=%BUILD%\startup_snapshot_status.v1.json
set SNAPDIR=%BUILD%\authoritative_order_snapshots
set TRADE_OUT=%BUILD%\startup_snapshot_trade.out
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
rmdir /s /q "%SNAPDIR%" >nul 2>nul

start "ASTU Startup Snapshot Seed Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%TRADE%" > "%TRADE_OUT%" 2>&1
if errorlevel 1 (
  type "%TRADE_OUT%"
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL SEED_REQUEST
  set RC=3
  goto cleanup
)
type "%TRADE_OUT%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%TRADE_OUT%"') do set ORDER_ID=%%A
if "!ORDER_ID!"=="" (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

python "%SOURCE%" ^
  --output-dir "%SNAPDIR%" ^
  --order-id "!ORDER_ID!" ^
  --state SIZING ^
  --cumulative-filled 0 ^
  --detail "matching startup snapshot"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL MATCHING_SNAPSHOT_PUBLISH
  set RC=5
  goto cleanup
)

start "ASTU Startup Snapshot Match Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%" ^
  --order-snapshot-dir "%SNAPDIR%" ^
  --max-order-snapshot-age-ms 60000
ping -n 3 127.0.0.1 >nul

python -c "import json,time; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['lifecycleState']=='READY', o; assert o['startupOrderSnapshotRequired'] is True; assert o['startupOrderTracked']==1, o; assert o['startupOrderMatched']==1, o; assert o['startupOrderMarkedUnknown']==0, o; assert o['startupOrderUnresolved']==0, o; assert o['orderTransitionCount']==4, o; assert o['reconciliationEventCount']==0, o; assert o['orderRoutingEnabled'] is False; print('STARTUP_ORDER_SNAPSHOT_MATCH=PASS')"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL MATCH_STATUS
  set RC=6
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

python "%SOURCE%" ^
  --output-dir "%SNAPDIR%" ^
  --order-id "!ORDER_ID!" ^
  --state WORKING ^
  --cumulative-filled 0 ^
  --detail "authoritative source disagrees with SIZING journal"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL MISMATCH_SNAPSHOT_PUBLISH
  set RC=7
  goto cleanup
)

start "ASTU Startup Snapshot Mismatch Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%" ^
  --order-snapshot-dir "%SNAPDIR%" ^
  --max-order-snapshot-age-ms 60000
ping -n 3 127.0.0.1 >nul

python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['startupOrderTracked']==1, o; assert o['startupOrderMatched']==0, o; assert o['startupOrderMarkedUnknown']==1, o; assert o['startupOrderUnresolved']==1, o; assert o['orderTransitionCount']==5, o; assert o['reconciliationEventCount']==1, o; assert o['orderRoutingEnabled'] is False; print('STARTUP_ORDER_SNAPSHOT_MISMATCH_TO_UNKNOWN=PASS')"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL UNKNOWN_STATUS
  set RC=8
  goto cleanup
)

"%RECON%" ^
  --order-id "!ORDER_ID!" ^
  --event-id STARTUP-WORKING-EVIDENCE ^
  --event WORKING ^
  --cumulative-filled 0 ^
  --detail "authoritative simulated working evidence"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL WORKING_EVIDENCE
  set RC=9
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['orderTransitionCount']==6, o; assert o['reconciliationEventCount']==2, o; assert o['startupOrderUnresolved']==1, o; assert o['orderRoutingEnabled'] is False; print('STARTUP_ORDER_SNAPSHOT_EVIDENCE_APPLIED=PASS')"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL EVIDENCE_STATUS
  set RC=10
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

python "%SOURCE%" ^
  --output-dir "%SNAPDIR%" ^
  --order-id "!ORDER_ID!" ^
  --state WORKING ^
  --cumulative-filled 0 ^
  --detail "resolved working startup snapshot"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL RESOLVED_SNAPSHOT_PUBLISH
  set RC=11
  goto cleanup
)

start "ASTU Startup Snapshot Resolved Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%" ^
  --order-snapshot-dir "%SNAPDIR%" ^
  --max-order-snapshot-age-ms 60000
ping -n 3 127.0.0.1 >nul

python -c "import json,time; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['startupOrderTracked']==1, o; assert o['startupOrderMatched']==1, o; assert o['startupOrderMarkedUnknown']==0, o; assert o['startupOrderUnresolved']==0, o; assert o['recoveredReconciliationEventsAtStartup']==2, o; assert o['reconciliationEventCount']==2, o; assert o['orderTransitionCount']==6, o; assert o['orderRoutingEnabled'] is False; age=int(time.time()*1000)-int(o['generatedUnixMs']); assert 0<=age<5000, age; print('STARTUP_ORDER_SNAPSHOT_RESOLVED_RESTART=PASS')"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL RESOLVED_RESTART
  set RC=12
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; rec=[x for x in rows if x.get('eventType')=='SIMULATION_RECONCILIATION_EVENT']; assert len(rec)==2, len(rec); assert rec[0]['reconciliationType']=='MARK_UNKNOWN'; assert rec[0]['toState']=='UNKNOWN_RECONCILE_REQUIRED'; assert rec[1]['reconciliationType']=='WORKING'; assert rec[1]['toState']=='WORKING'; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('STARTUP_ORDER_SNAPSHOT_JOURNAL=PASS')"
if errorlevel 1 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL JOURNAL
  set RC=13
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=PASS
  echo SIMULATION_ORDER_ID=!ORDER_ID!
  echo STARTUP_MISMATCH_FAIL_CLOSED=PASS
  echo EVIDENCE_REQUIRED_TO_RESOLVE=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo STARTUP_ORDER_SNAPSHOT_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
