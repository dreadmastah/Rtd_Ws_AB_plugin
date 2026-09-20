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
start "ASTU Simulation Stack Fixture" /b python "%LAUNCHER%" --risk-mode fixture --instrument-mode fixture --journal "%JOURNAL%" --status-dir "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json, pathlib; p=pathlib.Path(r'%RISKVIEW_JSON%'); assert p.exists(); o=json.loads(p.read_text(encoding='utf-8')); a=o['accountRiskObservation']; assert o['messageType']=='AccountRiskView.v1'; assert o['orderRoutingEnabled'] is False; assert o['sourceFresh'] is True; assert a['ready'] is True; assert a['riskState']=='NORMAL'; assert abs(a['riskCapital']-10250.0)<1e-9; assert abs(a['availableBalance']-9150.0)<1e-9; assert abs(a['grossNotional']-1000.0)<1e-9; assert abs(a['projectedGrossNotional']-1000.0)<1e-9; assert abs(a['marginBalance']-10250.0)<1e-9; assert abs(a['initialMargin']-100.0)<1e-9; assert abs(a['projectedEffectiveLeverage']-(1000.0/10250.0))<1e-9; assert abs(a['projectedMarginUtilization']-(100.0/10250.0))<1e-9; assert abs(a['projectedNetDirectionalNotional']-1000.0)<1e-9; assert pathlib.Path(r'%RISKVIEW_HTML%').exists(); h=pathlib.Path(r'%RISKVIEW_HTML%').read_text(encoding='utf-8'); assert 'READ ONLY' in h and 'No order controls exist in this view.' in h and 'Live account and projected headroom' in h; print('ACCOUNT_RISK_VIEW_SUPERVISED=PASS')"
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id stack-fixture-buy --action BUY --side LONG --expect ORDER_ROUTING_DISABLED
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
