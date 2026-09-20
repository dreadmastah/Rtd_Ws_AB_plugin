@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set JOURNAL=%BUILD%\order_fsm_restart_journal.jsonl
set STATUS=%BUILD%\order_fsm_restart_status.v1.json
set BEFORE=%BUILD%\order_fsm_restart_before.out
set AFTER=%BUILD%\order_fsm_restart_after.out
set RC=0

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)
if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)

del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%BEFORE%" >nul 2>nul
del /q "%AFTER%" >nul 2>nul

start "ASTU Order FSM Host 1" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" > "%BEFORE%" 2>&1
if errorlevel 1 (
  type "%BEFORE%"
  echo ORDER_FSM_RESTART_SMOKE=FAIL INITIAL_REQUEST
  set RC=3
  goto cleanup
)
type "%BEFORE%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%BEFORE%"') do set ORDER_ID=%%A
if "!ORDER_ID!"=="" (
  echo ORDER_FSM_RESTART_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)

findstr /C:"!ORDER_ID!" "%JOURNAL%" >nul
if errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL ORDER_ID_NOT_JOURNALED
  set RC=5
  goto cleanup
)

findstr /C:"\"toState\":\"SIZING\"" "%JOURNAL%" >nul
if errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL SIZING_NOT_JOURNALED
  set RC=6
  goto cleanup
)

findstr /C:"\"toState\":\"SUBMITTING\"" "%JOURNAL%" >nul
if not errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL SUBMITTING_MUST_NOT_EXIST
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Order FSM Host 2" /b "%HOST%" ^
  --synthetic ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json,time; o=json.load(open(r'%STATUS%',encoding='utf-8')); assert o['lifecycleState']=='READY'; assert o['orderRoutingEnabled'] is False; assert o['recoveredOrdersAtStartup']==1, o; assert o['trackedOrders']==1, o; assert o['orderTransitionCount']==4, o; assert o['positionProvider']=='NONE'; age=int(time.time()*1000)-int(o['generatedUnixMs']); assert 0<=age<5000, age; print('ORDER_FSM_RECOVERY_STATUS=PASS')"
if errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL RECOVERY_STATUS
  set RC=8
  goto cleanup
)

"%CLIENT%" --expect-duplicate > "%AFTER%" 2>&1
if errorlevel 1 (
  type "%AFTER%"
  echo ORDER_FSM_RESTART_SMOKE=FAIL DUPLICATE_AFTER_RESTART
  set RC=9
  goto cleanup
)
type "%AFTER%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%AFTER%"') do set AFTER_ORDER_ID=%%A
if not "!AFTER_ORDER_ID!"=="!ORDER_ID!" (
  echo ORDER_FSM_RESTART_SMOKE=FAIL ORDER_ID_CHANGED
  echo BEFORE=!ORDER_ID!
  echo AFTER=!AFTER_ORDER_ID!
  set RC=10
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; o=json.load(open(r'%STATUS%',encoding='utf-8')); assert o['recoveredOrdersAtStartup']==1, o; assert o['trackedOrders']==1, o; assert o['orderTransitionCount']==4, o; assert o['lastDecisionCode']=='DUPLICATE_REQUEST', o; assert o['orderRoutingEnabled'] is False; print('ORDER_FSM_DUPLICATE_RECOVERY=PASS')"
if errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL DUPLICATE_STATUS
  set RC=11
  goto cleanup
)

findstr /C:"\"exchangeSubmissionAttempted\":true" "%JOURNAL%" >nul
if not errorlevel 1 (
  echo ORDER_FSM_RESTART_SMOKE=FAIL EXCHANGE_SUBMISSION_FLAG
  set RC=12
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo ORDER_FSM_RESTART_SMOKE=PASS
  echo SIMULATION_ORDER_ID=!ORDER_ID!
  echo RECOVERED_ORDERS_AT_STARTUP=1
  echo TRACKED_ORDERS=1
  echo ORDER_TRANSITIONS=4
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo ORDER_FSM_RESTART_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
