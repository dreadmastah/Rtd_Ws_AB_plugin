@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set JOURNAL=%BUILD%\net_directional_risk_journal.jsonl
set STATUS=%BUILD%\net_directional_risk_status.v1.json
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

start "ASTU Net Directional Risk Host 1" /b "%HOST%" ^
  --synthetic ^
  --synthetic-net-directional-notional 0 ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-net-directional-notional 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id NET-LONG-1 --symbol BTCUSDT --side LONG --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL LONG_FIRST
  set RC=3
  goto cleanup
)

"%CLIENT%" --case-id NET-LONG-2 --symbol ETHUSDT --side LONG --expect RISK_BLOCKED
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL LONG_LIMIT
  set RC=4
  goto cleanup
)

"%CLIENT%" --case-id NET-SHORT-1 --symbol SOLUSDT --side SHORT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL OPPOSITE_SIDE_OFFSET
  set RC=5
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert abs(float(o['maxNetDirectionalNotional'])-10.0)<1e-12,o; assert o['activeExposureReservations']==2,o; assert abs(float(o['reservedGrossNotional'])-20.0)<1e-9,o; assert abs(float(o['reservedNetDirectionalNotional']))<1e-9,o; assert o['orderRoutingEnabled'] is False; print('NET_DIRECTIONAL_OFFSET=PASS')"
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL LIVE_STATUS
  set RC=6
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Net Directional Risk Host 2" /b "%HOST%" ^
  --synthetic ^
  --synthetic-net-directional-notional 0 ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-net-directional-notional 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['recoveredActiveExposureReservationsAtStartup']==2,o; assert o['activeExposureReservations']==2,o; assert abs(float(o['reservedNetDirectionalNotional']))<1e-9,o; print('NET_DIRECTIONAL_RESTART=PASS')"
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL RESTART_STATUS
  set RC=7
  goto cleanup
)

"%CLIENT%" --case-id NET-LONG-3 --symbol BNBUSDT --side LONG --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL RESTART_HEADROOM
  set RC=8
  goto cleanup
)

"%CLIENT%" --case-id NET-LONG-4 --symbol XRPUSDT --side LONG --expect RISK_BLOCKED
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL RESTART_LONG_LIMIT
  set RC=9
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['activeExposureReservations']==3,o; assert abs(float(o['reservedNetDirectionalNotional'])-10.0)<1e-9,o; assert o['orderRoutingEnabled'] is False; print('NET_DIRECTIONAL_RESTART_HEADROOM=PASS')"
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL FINAL_STATUS
  set RC=10
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; creates=[x for x in rows if x.get('eventType')=='EXPOSURE_RESERVATION_CREATED']; assert len(creates)==3,len(creates); assert [x['side'] for x in creates]==['LONG','SHORT','LONG'],creates; signed=sum((1 if x['side']=='LONG' else -1)*float(x['reservedGrossNotional']) for x in creates); assert abs(signed-10.0)<1e-9,signed; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('NET_DIRECTIONAL_JOURNAL=PASS')"
if errorlevel 1 (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL JOURNAL
  set RC=11
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo NET_DIRECTIONAL_RISK_SMOKE=PASS
  echo LONG_DIRECTION_LIMIT=PASS
  echo SHORT_OFFSET=PASS
  echo RESTART_SIGNED_RESERVATIONS=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo NET_DIRECTIONAL_RISK_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
