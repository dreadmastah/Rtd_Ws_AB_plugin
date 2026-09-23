@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set JOURNAL=%BUILD%\loss_drawdown_journal.jsonl
set STATUS=%BUILD%\loss_drawdown_status.v1.json
set BASELINE=%BUILD%\account_loss_baseline.v1.json
set RC=0

if not exist "%HOST%" exit /b 2
if not exist "%CLIENT%" exit /b 2

del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%BASELINE%" >nul 2>nul

rem Phase A: seed UTC daily/weekly baseline.
start "ASTU Loss Baseline Seed" /b "%HOST%" ^
  --synthetic ^
  --synthetic-risk-capital 1000 ^
  --synthetic-margin-balance 1000 ^
  --max-daily-risk-capital-loss 50 ^
  --max-weekly-risk-capital-loss 100 ^
  --account-loss-baseline-file "%BASELINE%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id LOSS-SEED --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo LOSS_DRAWDOWN_SMOKE=FAIL BASELINE_SEED
  set RC=3
  goto cleanup
)

python -c "import json, pathlib; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); b=json.load(open(r'%BASELINE%',encoding='utf-8')); assert o['accountLossBaselineEnabled'] is True,o; assert o['accountLossMetricsReady'] is True,o; assert abs(float(o['dailyStartRiskCapital'])-1000.0)<1e-9,o; assert abs(float(o['dailyRiskCapitalLoss']))<1e-9,o; assert b['messageType']=='AccountLossBaselineState.v1',b; assert abs(float(b['dailyStartRiskCapital'])-1000.0)<1e-9,b; print('LOSS_BASELINE_SEED=PASS')"
if errorlevel 1 (
  set RC=4
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Phase B: persisted daily Risk Capital loss blocks after restart.
start "ASTU Daily Loss Block" /b "%HOST%" ^
  --synthetic ^
  --synthetic-risk-capital 940 ^
  --synthetic-margin-balance 1000 ^
  --max-daily-risk-capital-loss 50 ^
  --max-weekly-risk-capital-loss 100 ^
  --account-loss-baseline-file "%BASELINE%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id LOSS-DAILY-BLOCK --expect RISK_BLOCKED
if errorlevel 1 (
  echo LOSS_DRAWDOWN_SMOKE=FAIL DAILY_LOSS_LIMIT
  set RC=5
  goto cleanup
)

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['accountLossMetricsReady'] is True,o; assert abs(float(o['dailyStartRiskCapital'])-1000.0)<1e-9,o; assert abs(float(o['dailyRiskCapitalLoss'])-60.0)<1e-9,o; assert abs(float(o['weeklyRiskCapitalLoss'])-60.0)<1e-9,o; assert abs(float(o['maxDailyRiskCapitalLoss'])-50.0)<1e-9,o; print('DAILY_RISK_CAPITAL_LOSS_BLOCK=PASS')"
if errorlevel 1 (
  set RC=6
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul
del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul
del /q "%BASELINE%" >nul 2>nul

rem Phase C: seed margin-balance total-PnL baseline and high-water.
start "ASTU Drawdown Seed" /b "%HOST%" ^
  --synthetic ^
  --synthetic-risk-capital 1000 ^
  --synthetic-margin-balance 1000 ^
  --max-daily-total-pnl-loss 200 ^
  --max-account-drawdown 100 ^
  --account-loss-baseline-file "%BASELINE%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id DD-SEED --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo LOSS_DRAWDOWN_SMOKE=FAIL DRAWDOWN_SEED
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Phase D: higher reconciled margin balance advances persisted high-water.
start "ASTU Drawdown High Water" /b "%HOST%" ^
  --synthetic ^
  --synthetic-risk-capital 1000 ^
  --synthetic-margin-balance 1100 ^
  --max-daily-total-pnl-loss 200 ^
  --max-account-drawdown 100 ^
  --account-loss-baseline-file "%BASELINE%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); b=json.load(open(r'%BASELINE%',encoding='utf-8')); assert abs(float(o['highWaterMarginBalance'])-1100.0)<1e-9,o; assert abs(float(o['accountDrawdown']))<1e-9,o; assert abs(float(b['highWaterMarginBalance'])-1100.0)<1e-9,b; print('ACCOUNT_HIGH_WATER_ADVANCE=PASS')"
if errorlevel 1 (
  set RC=8
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Phase E: drawdown from persisted high-water blocks new exposure.
start "ASTU Drawdown Block" /b "%HOST%" ^
  --synthetic ^
  --synthetic-risk-capital 1000 ^
  --synthetic-margin-balance 950 ^
  --max-account-drawdown 100 ^
  --account-loss-baseline-file "%BASELINE%" ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id DD-BLOCK --expect RISK_BLOCKED
if errorlevel 1 (
  echo LOSS_DRAWDOWN_SMOKE=FAIL DRAWDOWN_LIMIT
  set RC=9
  goto cleanup
)

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%STATUS%'); assert o['accountLossMetricsReady'] is True,o; assert abs(float(o['highWaterMarginBalance'])-1100.0)<1e-9,o; assert abs(float(o['accountDrawdown'])-150.0)<1e-9,o; assert abs(float(o['maxAccountDrawdown'])-100.0)<1e-9,o; assert o['orderRoutingEnabled'] is False; print('ACCOUNT_DRAWDOWN_BLOCK=PASS')"
if errorlevel 1 (
  set RC=10
  goto cleanup
)

python -c "import json; rows=[json.loads(x) for x in open(r'%JOURNAL%',encoding='utf-8') if x.strip()]; assert not any(x.get('toState')=='SUBMITTING' for x in rows); assert not any(x.get('exchangeSubmissionAttempted') is True for x in rows); print('LOSS_DRAWDOWN_NO_SUBMISSION=PASS')"
if errorlevel 1 (
  set RC=11
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo LOSS_DRAWDOWN_SMOKE=PASS
  echo DAILY_WEEKLY_BASELINE_PERSISTENCE=PASS
  echo DAILY_LOSS_BLOCK=PASS
  echo HIGH_WATER_DRAWDOWN_BLOCK=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo LOSS_DRAWDOWN_SMOKE=FAIL RC=!RC!
)
exit /b !RC!
