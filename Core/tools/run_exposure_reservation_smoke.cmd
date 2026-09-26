@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set JOURNAL=%BUILD%\exposure_reservation_journal.jsonl
set STATUS=%BUILD%\exposure_reservation_status.v1.json
set FIRST=%BUILD%\exposure_reservation_first.out
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

start "ASTU Exposure Reservation Host 1" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 10 ^
  --synthetic-max-open-positions 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id RES-1 --expect ORDER_ROUTING_DISABLED > "%FIRST%" 2>&1
if errorlevel 1 (
  type "%FIRST%"
  echo EXPOSURE_RESERVATION_SMOKE=FAIL FIRST_ACCEPT
  set RC=3
  goto cleanup
)
type "%FIRST%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%FIRST%"') do set ORDER_ID=%%A
for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulatedQuantity=" "%FIRST%"') do set ORDER_QTY=%%A
if "!ORDER_ID!"=="" (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)
if "!ORDER_QTY!"=="" (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL ORDER_QTY_MISSING
  set RC=5
  goto cleanup
)

"%CLIENT%" --case-id RES-2 --expect RISK_BLOCKED
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL RESERVED_HEADROOM_NOT_BLOCKED
  set RC=6
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['activeExposureReservations']==1, o; assert abs(float(o['reservedGrossNotional'])-10.0)<1e-9, o; assert o['reservedPositionSlots']==1, o; assert o['exposureReservationCreateCount']==1, o; assert o['exposureReservationReleaseCount']==0, o; assert o['orderRoutingEnabled'] is False; print('EXPOSURE_RESERVATION_LIVE_BLOCK=PASS')"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL LIVE_STATUS
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Exposure Reservation Host 2" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 10 ^
  --synthetic-max-open-positions 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['recoveredActiveExposureReservationsAtStartup']==1, o; assert o['activeExposureReservations']==1, o; assert abs(float(o['reservedGrossNotional'])-10.0)<1e-9, o; assert o['reservedPositionSlots']==1, o; assert o['exposureReservationCreateCount']==1, o; assert o['exposureReservationReleaseCount']==0, o; print('EXPOSURE_RESERVATION_RESTART_RECOVERY=PASS')"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL RESTART_STATUS
  set RC=8
  goto cleanup
)

"%CLIENT%" --case-id RES-3 --expect RISK_BLOCKED
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL RESTART_HEADROOM_NOT_BLOCKED
  set RC=9
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id RES-UNKNOWN --event MARK_UNKNOWN --cumulative-filled 0 --detail "reservation release smoke unknown"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL MARK_UNKNOWN
  set RC=10
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id RES-WORKING --event WORKING --cumulative-filled 0 --detail "reservation release smoke working"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL WORKING
  set RC=11
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id RES-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!" --detail "reservation release smoke filled"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL FILLED
  set RC=12
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['activeExposureReservations']==0, o; assert abs(float(o['reservedGrossNotional']))<1e-12, o; assert o['reservedPositionSlots']==0, o; assert o['exposureReservationReleaseCount']==1, o; print('EXPOSURE_RESERVATION_TERMINAL_RELEASE=PASS')"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL RELEASE_STATUS
  set RC=13
  goto cleanup
)

"%CLIENT%" --case-id RES-4 --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL HEADROOM_NOT_RESTORED
  set RC=14
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['activeExposureReservations']==1, o; assert abs(float(o['reservedGrossNotional'])-10.0)<1e-9, o; assert o['exposureReservationCreateCount']==2, o; assert o['exposureReservationReleaseCount']==1, o; assert o['orderRoutingEnabled'] is False; print('EXPOSURE_RESERVATION_HEADROOM_REUSED=PASS')"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL REUSED_STATUS
  set RC=15
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; creates=[x for x in rows if x.get('eventType')=='EXPOSURE_RESERVATION_CREATED']; releases=[x for x in rows if x.get('eventType')=='EXPOSURE_RESERVATION_RELEASED']; assert len(creates)==2, len(creates); assert len(releases)==1, len(releases); assert releases[0]['terminalState']=='FILLED'; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('EXPOSURE_RESERVATION_JOURNAL=PASS')"
if errorlevel 1 (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL JOURNAL
  set RC=16
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo EXPOSURE_RESERVATION_SMOKE=PASS
  echo RESTART_RECOVERY=PASS
  echo PROJECTED_GROSS_HEADROOM_BLOCK=PASS
  echo TERMINAL_RELEASE=PASS
  echo HEADROOM_REUSE=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo EXPOSURE_RESERVATION_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
