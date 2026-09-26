@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set REPO=%ROOT%\..
set BUILD=%REPO%\build\core
set LAUNCHER=%ROOT%\stack\autotrader_sim_launcher.py
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%REPO%\CleanRoomR2\stack\runtime\autotrader_status
set BRIDGE=%REPO%\CleanRoomR2\stack\identity_bridge.py
set PIDFILE=%ROOT%\runtime\autotrader_sim_pids.json
set RISK=%BUILD%\execution_restart_risk.v1.json
set JOURNAL=%BUILD%\execution_restart_journal.jsonl
set EXECSTATUS=%BUILD%\execution_restart_status.v1.json
set RC=0

if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)

del /q "%RISK%" >nul 2>nul
del /q "%JOURNAL%" >nul 2>nul
del /q "%EXECSTATUS%" >nul 2>nul

python "%BRIDGE%" --once
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL INITIAL_STATUS_REFRESH
  exit /b 3
)

start "ASTU Execution Restart Supervisor" /b python "%LAUNCHER%" ^
  --risk-mode fixture ^
  --risk-file "%RISK%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%EXECSTATUS%" ^
  --status-dir "%STATUS%" ^
  --restart-delay-seconds 1

ping -n 4 127.0.0.1 >nul

if not exist "%PIDFILE%" (
  echo EXECUTION_RESTART_SMOKE=FAIL PIDFILE_MISSING
  set RC=4
  goto cleanup
)

for /f "delims=" %%P in ('python -c "import json; print(json.load(open(r'%PIDFILE%'))['processes']['execution']['pid'])"') do set OLD_PID=%%P
if "!OLD_PID!"=="" (
  echo EXECUTION_RESTART_SMOKE=FAIL OLD_PID_MISSING
  set RC=5
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id restart-before --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL PRECRASH_REQUEST
  set RC=6
  goto cleanup
)

taskkill /PID !OLD_PID! /F >nul 2>nul
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL CANNOT_KILL_EXECUTION PID=!OLD_PID!
  set RC=7
  goto cleanup
)

ping -n 5 127.0.0.1 >nul

python "%BRIDGE%" --once
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL POSTCRASH_STATUS_REFRESH
  set RC=8
  goto cleanup
)

for /f "delims=" %%P in ('python -c "import json; print(json.load(open(r'%PIDFILE%'))['processes']['execution']['pid'])"') do set NEW_PID=%%P
if "!NEW_PID!"=="" (
  echo EXECUTION_RESTART_SMOKE=FAIL NEW_PID_MISSING
  set RC=9
  goto cleanup
)
if "!NEW_PID!"=="!OLD_PID!" (
  echo EXECUTION_RESTART_SMOKE=FAIL EXECUTION_PID_DID_NOT_CHANGE PID=!NEW_PID!
  set RC=10
  goto cleanup
)

tasklist /FI "PID eq !NEW_PID!" /FO CSV /NH | findstr /C:"!NEW_PID!" >nul
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL NEW_EXECUTION_NOT_ALIVE PID=!NEW_PID!
  set RC=11
  goto cleanup
)

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id restart-after --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL POSTCRASH_REQUEST
  set RC=12
  goto cleanup
)

ping -n 3 127.0.0.1 >nul

python -c "import json,time; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%EXECSTATUS%'); assert o['schemaVersion']==1; assert o['messageType']=='ExecutionStatus.v1'; assert o['processId']==int('!NEW_PID!'); assert o['lifecycleState']=='READY'; assert o['journalReady'] is True; assert o['pipeReady'] is True; assert o['orderRoutingEnabled'] is False; assert o['requestsSeen']>=1; age=int(time.time()*1000)-int(o['generatedUnixMs']); assert 0<=age<5000, age; print('EXECUTION_STATUS_RESTART_CHECK=PASS')"
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL EXECUTION_STATUS
  set RC=13
  goto cleanup
)

findstr /C:"SIMULATION_DECISION" "%JOURNAL%" >nul
if errorlevel 1 (
  echo EXECUTION_RESTART_SMOKE=FAIL JOURNAL_DECISIONS_MISSING
  set RC=14
  goto cleanup
)

:cleanup
python "%LAUNCHER%" --stop >nul 2>nul

if !RC! EQU 0 (
  echo EXECUTION_RESTART_SMOKE=PASS
  echo OLD_EXECUTION_PID=!OLD_PID!
  echo NEW_EXECUTION_PID=!NEW_PID!
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo EXECUTION_RESTART_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
