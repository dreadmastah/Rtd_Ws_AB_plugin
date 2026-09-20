@echo off
setlocal
set ROOT=%~dp0..
set REPO=%ROOT%\..
set BUILD=%REPO%\build\core
set LAUNCHER=%ROOT%\stack\autotrader_sim_launcher.py
set CLIENT=%BUILD%\Release\astu_trade_pipe_live_smoke.exe
set STATUS=%REPO%\CleanRoomR2\stack\runtime\autotrader_status
set JOURNAL=%BUILD%\sim_stack_fixture_journal.jsonl
set RISKVIEW_JSON=%ROOT%\runtime\account_risk_view.v1.json
set RISKVIEW_HTML=%ROOT%\runtime\account_risk_view.html
set SYMBOLRISK=%ROOT%\runtime\symbol_risk_status.v1.json

if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)
if not exist "%STATUS%\BTCUSDT.json" (
  echo ERROR: missing %STATUS%\BTCUSDT.json
  exit /b 3
)

python "%REPO%\CleanRoomR2\stack\identity_bridge.py" --once
if errorlevel 1 (
  echo SIM_STACK_FIXTURE_SMOKE=FAIL STATUS_REFRESH
  exit /b 3
)

del /q "%JOURNAL%" >nul 2>nul
del /q "%RISKVIEW_JSON%" >nul 2>nul
del /q "%RISKVIEW_HTML%" >nul 2>nul
del /q "%SYMBOLRISK%" >nul 2>nul
start "ASTU Simulation Stack Fixture" /b python "%LAUNCHER%" --risk-mode fixture --instrument-mode fixture --journal "%JOURNAL%" --status-dir "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json,pathlib,time; p=pathlib.Path(r'%RISKVIEW_JSON%'); sp=pathlib.Path(r'%SYMBOLRISK%'); hp=pathlib.Path(r'%RISKVIEW_HTML%'); deadline=time.time()+15; last='not-ready'; ok=False
while time.time()<deadline:
 try:
  if not (p.exists() and sp.exists() and hp.exists()): raise AssertionError('artifacts missing')
  o=json.loads(p.read_text(encoding='utf-8')); a=o['accountRiskObservation']; s=o['symbolRisk']; rows={r['symbol']:r for r in s['symbols']}; raw=json.loads(sp.read_text(encoding='utf-8')); h=hp.read_text(encoding='utf-8')
  assert o['messageType']=='AccountRiskView.v1'; assert o['orderRoutingEnabled'] is False; assert o['sourceFresh'] is True; assert a['ready'] is True; assert a['riskState']=='NORMAL'; assert abs(a['riskCapital']-10250.0)<1e-9; assert abs(a['availableBalance']-9150.0)<1e-9; assert abs(a['grossNotional']-1000.0)<1e-9; assert abs(a['projectedGrossNotional']-1000.0)<1e-9; assert abs(a['marginBalance']-10250.0)<1e-9; assert abs(a['initialMargin']-100.0)<1e-9; assert abs(a['projectedEffectiveLeverage']-(1000.0/10250.0))<1e-9; assert abs(a['projectedMarginUtilization']-(100.0/10250.0))<1e-9; assert abs(a['projectedNetDirectionalNotional']-1000.0)<1e-9; assert s['ready'] is True; assert len(rows)==12; assert rows['BTCUSDT']['positionMode']=='LONG'; assert abs(rows['BTCUSDT']['currentNotional']-1000.0)<1e-9; assert rows['ETHUSDT']['positionMode']=='FLAT'; assert abs(rows['ETHUSDT']['currentNotional'])<1e-9; assert raw['orderRoutingEnabled'] is False; assert len(raw['symbols'])==12; assert 'READ ONLY' in h and 'No order controls exist in this view.' in h and 'Live account and projected headroom' in h and 'Per-symbol projected exposure' in h
  ok=True; break
 except Exception as e:
  last=repr(e); time.sleep(.25)
assert ok, last
print('ACCOUNT_RISK_VIEW_SUPERVISED=PASS')"
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id stack-fixture-buy --action BUY --side LONG --expect ORDER_ROUTING_DISABLED
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

ping -n 3 127.0.0.1 >nul
python -c "import json,pathlib,time; p=pathlib.Path(r'%RISKVIEW_JSON%'); deadline=time.time()+10; last='not-ready'; ok=False
while time.time()<deadline:
 try:
  o=json.loads(p.read_text(encoding='utf-8')); rows={r['symbol']:r for r in o['symbolRisk']['symbols']}; b=rows['BTCUSDT']; assert b['positionReady'] is True; assert b['activeReservations']==1, b; assert b['reservedGrossNotional']>0, b; assert b['projectedNotional']>b['currentNotional'], b; assert o['orderRoutingEnabled'] is False
  ok=True; break
 except Exception as e:
  last=repr(e); time.sleep(.25)
assert ok, last
print('SYMBOL_RISK_RESERVATION_PROJECTION=PASS')"
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id stack-fixture-scale-in --action SCALE_IN --side LONG --trigger-price 1000 --expect ORDER_ROUTING_DISABLED
set RC=%ERRORLEVEL%

:cleanup
python "%LAUNCHER%" --stop >nul 2>nul

if %RC% EQU 0 (
  echo SIM_STACK_FIXTURE_SMOKE=PASS
) else (
  echo SIM_STACK_FIXTURE_SMOKE=FAIL RC=%RC%
)

exit /b %RC%
