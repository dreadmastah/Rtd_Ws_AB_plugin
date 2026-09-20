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

python "%ROOT%\tools\verify_account_risk_view_smoke.py" ^
  --mode ready ^
  --view-json "%RISKVIEW_JSON%" ^
  --symbol-json "%SYMBOLRISK%" ^
  --html "%RISKVIEW_HTML%" ^
  --timeout-seconds 15
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

"%CLIENT%" --status-dir "%STATUS%" --symbol BTCUSDT --case-id stack-fixture-buy --action BUY --side LONG --expect ORDER_ROUTING_DISABLED
set RC=%ERRORLEVEL%
if not %RC% EQU 0 goto cleanup

ping -n 3 127.0.0.1 >nul
python "%ROOT%\tools\verify_account_risk_view_smoke.py" ^
  --mode reservation ^
  --view-json "%RISKVIEW_JSON%" ^
  --timeout-seconds 10
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
