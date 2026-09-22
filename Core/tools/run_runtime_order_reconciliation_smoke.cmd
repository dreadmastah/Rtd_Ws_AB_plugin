@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set TRADE=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set SOURCE=%ROOT%\order_state\simulated_order_state_source.py
set JOURNAL=%BUILD%\runtime_order_reconcile_journal.jsonl
set STATUS=%BUILD%\runtime_order_reconcile_status.v1.json
set SNAPDIR=%BUILD%\runtime_order_reconcile_snapshots
set TRADE_OUT=%BUILD%\runtime_order_reconcile_trade.out
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

start "ASTU Runtime Reconcile Seed Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%TRADE%" > "%TRADE_OUT%" 2>&1
if errorlevel 1 (
  type "%TRADE_OUT%"
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL SEED_REQUEST
  set RC=3
  goto cleanup
)
type "%TRADE_OUT%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%TRADE_OUT%"') do set ORDER_ID=%%A
if "!ORDER_ID!"=="" (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL ORDER_ID_MISSING
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
  --detail "runtime sweep initial match"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL INITIAL_SNAPSHOT
  set RC=5
  goto cleanup
)

start "ASTU Runtime Reconcile Host" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%" ^
  --order-snapshot-dir "%SNAPDIR%" ^
  --max-order-snapshot-age-ms 60000 ^
  --order-reconcile-interval-ms 250
ping -n 3 127.0.0.1 >nul

python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['startupOrderMatched']==1, o; assert o['runtimeOrderReconciliationEnabled'] is True; assert o['runtimeOrderSweepCount']>=1, o; assert o['runtimeOrderTrackedNonterminal']==1, o; assert o['runtimeOrderMatched']==1, o; assert o['runtimeOrderUnresolved']==0, o; assert o['runtimeOrderSourceUnavailable']==0, o; print('RUNTIME_ORDER_RECONCILE_INITIAL_MATCH=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL INITIAL_MATCH
  set RC=6
  goto cleanup
)

python "%SOURCE%" ^
  --output-dir "%SNAPDIR%" ^
  --order-id "!ORDER_ID!" ^
  --state WORKING ^
  --cumulative-filled 0 ^
  --detail "runtime authoritative state changed to working"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL WORKING_SNAPSHOT
  set RC=7
  goto cleanup
)

ping -n 3 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['runtimeOrderUnresolved']==1, o; assert o['runtimeOrderSourceUnavailable']==0, o; assert o['reconciliationEventCount']>=1, o; print('RUNTIME_ORDER_RECONCILE_MISMATCH_TO_UNKNOWN=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL MISMATCH_TO_UNKNOWN
  set RC=8
  goto cleanup
)

"%RECON%" ^
  --order-id "!ORDER_ID!" ^
  --event-id RUNTIME-WORKING-EVIDENCE-1 ^
  --event WORKING ^
  --cumulative-filled 0 ^
  --detail "runtime working evidence"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL WORKING_EVIDENCE_1
  set RC=9
  goto cleanup
)

ping -n 3 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['runtimeOrderMatched']==1, o; assert o['runtimeOrderUnresolved']==0, o; assert o['runtimeOrderSourceUnavailable']==0, o; print('RUNTIME_ORDER_RECONCILE_EVIDENCE_RESOLVED=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL EVIDENCE_RESOLUTION
  set RC=10
  goto cleanup
)

del /q "%SNAPDIR%\!ORDER_ID!.json" >nul 2>nul
ping -n 3 127.0.0.1 >nul

python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['runtimeOrderUnresolved']==1, o; assert o['runtimeOrderSourceUnavailable']==1, o; print('RUNTIME_ORDER_RECONCILE_MISSING_SOURCE=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL MISSING_SOURCE
  set RC=11
  goto cleanup
)

python "%SOURCE%" ^
  --output-dir "%SNAPDIR%" ^
  --order-id "!ORDER_ID!" ^
  --state WORKING ^
  --cumulative-filled 0 ^
  --detail "runtime source restored"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL RESTORE_SNAPSHOT
  set RC=12
  goto cleanup
)

ping -n 3 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['runtimeOrderUnresolved']==1, o; assert o['runtimeOrderSourceUnavailable']==0, o; print('RUNTIME_ORDER_RECONCILE_REQUIRES_EVIDENCE=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL AUTO_RESOLVED_WITHOUT_EVIDENCE
  set RC=13
  goto cleanup
)

"%RECON%" ^
  --order-id "!ORDER_ID!" ^
  --event-id RUNTIME-WORKING-EVIDENCE-2 ^
  --event WORKING ^
  --cumulative-filled 0 ^
  --detail "explicit evidence after source restoration"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL WORKING_EVIDENCE_2
  set RC=14
  goto cleanup
)

ping -n 3 127.0.0.1 >nul
python -c "import json; o=__import__('status_json_reader').read_json(r'%STATUS%'); assert o['runtimeOrderMatched']==1, o; assert o['runtimeOrderUnresolved']==0, o; assert o['runtimeOrderSourceUnavailable']==0, o; assert o['runtimeOrderSweepErrors']==0, o; assert o['orderRoutingEnabled'] is False; print('RUNTIME_ORDER_RECONCILE_FINAL_MATCH=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL FINAL_MATCH
  set RC=15
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; rec=[x for x in rows if x.get('eventType')=='SIMULATION_RECONCILIATION_EVENT']; types=[x['reconciliationType'] for x in rec]; assert types.count('MARK_UNKNOWN')==2, types; assert types.count('WORKING')==2, types; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('RUNTIME_ORDER_RECONCILE_JOURNAL=PASS')"
if errorlevel 1 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL JOURNAL
  set RC=16
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=PASS
  echo SIMULATION_ORDER_ID=!ORDER_ID!
  echo RUNTIME_MISMATCH_TO_UNKNOWN=PASS
  echo MISSING_SOURCE_TO_UNKNOWN=PASS
  echo EXPLICIT_EVIDENCE_REQUIRED=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo RUNTIME_ORDER_RECONCILE_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
