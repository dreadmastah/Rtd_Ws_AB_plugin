@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set INCOME=%ROOT%\account\binance_usdm_income_reconciler.py
set FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_income_v1.json
set STATUS=%BUILD%\realized_pnl_status.v1.json
set STATE=%BUILD%\realized_pnl_accumulator.v1.json
set EXECSTATUS=%BUILD%\realized_pnl_execution_status.v1.json
set JOURNAL=%BUILD%\realized_pnl_risk_journal.jsonl
set RC=0

if not exist "%HOST%" exit /b 2
if not exist "%CLIENT%" exit /b 2
if not exist "%INCOME%" exit /b 2

del /q "%STATUS%" >nul 2>nul
del /q "%STATE%" >nul 2>nul
del /q "%EXECSTATUS%" >nul 2>nul
del /q "%JOURNAL%" >nul 2>nul

python "%INCOME%" --once --fixture "%FIXTURE%" --output "%STATUS%" --state "%STATE%"
if errorlevel 1 (
  echo REALIZED_PNL_RISK_SMOKE=FAIL INCOME_FIXTURE
  exit /b 3
)

python -c "import json; s=json.load(open(r'%STATUS%',encoding='utf-8')); st=json.load(open(r'%STATE%',encoding='utf-8')); assert s['reconciled'] is True,s; assert abs(float(s['dailyRealizedTradePnl'])+60.0)<1e-9,s; assert abs(float(s['weeklyRealizedTradePnl'])+60.0)<1e-9,s; assert abs(float(s['dailyRealizedTradeLoss'])-60.0)<1e-9,s; assert abs(float(s['weeklyRealizedTradeLoss'])-60.0)<1e-9,s; assert abs(float(s['dailyFundingFee'])-1.0)<1e-9,s; assert abs(float(s['dailyCommission'])+2.0)<1e-9,s; assert s['ignoredIncomeRecords']==1,s; assert st['messageType']=='RealizedPnlAccumulatorState.v1',st; print('REALIZED_PNL_FIXTURE_RECONCILIATION=PASS')"
if errorlevel 1 exit /b 4

rem Daily exact realized-trade loss gate.
start "ASTU Realized PnL Daily Gate" /b "%HOST%" ^
  --synthetic ^
  --realized-pnl-status-file "%STATUS%" ^
  --max-realized-pnl-status-age-ms 90000 ^
  --max-daily-realized-trade-loss 50 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%EXECSTATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id REALIZED-DAILY --expect RISK_BLOCKED
if errorlevel 1 (
  echo REALIZED_PNL_RISK_SMOKE=FAIL DAILY_GATE
  set RC=5
  goto cleanup
)

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%EXECSTATUS%'); assert o['realizedPnlRequired'] is True,o; assert o['realizedPnlReady'] is True,o; assert o['realizedPnlProvider']=='FILE_BACKED_BINANCE_INCOME_V1',o; assert abs(float(o['dailyRealizedTradeLoss'])-60.0)<1e-9,o; assert abs(float(o['weeklyRealizedTradeLoss'])-60.0)<1e-9,o; assert abs(float(o['dailyFundingFee'])-1.0)<1e-9,o; assert abs(float(o['dailyCommission'])+2.0)<1e-9,o; assert o['realizedPnlIgnoredIncomeRecords']==1,o; assert abs(float(o['maxDailyRealizedTradeLoss'])-50.0)<1e-9,o; assert o['orderRoutingEnabled'] is False,o; print('REALIZED_PNL_DAILY_GATE=PASS')"
if errorlevel 1 (
  set RC=6
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Weekly exact realized-trade loss gate.
start "ASTU Realized PnL Weekly Gate" /b "%HOST%" ^
  --synthetic ^
  --realized-pnl-status-file "%STATUS%" ^
  --max-realized-pnl-status-age-ms 90000 ^
  --max-weekly-realized-trade-loss 50 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%EXECSTATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id REALIZED-WEEKLY --expect RISK_BLOCKED
if errorlevel 1 (
  echo REALIZED_PNL_RISK_SMOKE=FAIL WEEKLY_GATE
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul
del /q "%STATUS%" >nul 2>nul

rem Required income evidence missing => fail closed.
start "ASTU Realized PnL Missing Evidence" /b "%HOST%" ^
  --synthetic ^
  --realized-pnl-status-file "%STATUS%" ^
  --max-realized-pnl-status-age-ms 90000 ^
  --max-daily-realized-trade-loss 50 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%EXECSTATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id REALIZED-MISSING --expect ACCOUNT_NOT_RECONCILED
if errorlevel 1 (
  echo REALIZED_PNL_RISK_SMOKE=FAIL MISSING_EVIDENCE
  set RC=8
  goto cleanup
)

python -c "import json; import sys; sys.path.insert(0,r'%ROOT%\tools'); from status_json_reader import read_json; o=read_json(r'%EXECSTATUS%'); assert o['realizedPnlRequired'] is True,o; assert o['realizedPnlReady'] is False,o; assert o['orderRoutingEnabled'] is False,o; print('REALIZED_PNL_MISSING_EVIDENCE_FAIL_CLOSED=PASS')"
if errorlevel 1 set RC=9

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo REALIZED_PNL_RISK_SMOKE=PASS
  echo DAILY_REALIZED_TRADE_LOSS=PASS
  echo WEEKLY_REALIZED_TRADE_LOSS=PASS
  echo FUNDING_COMMISSION_SEPARATION=PASS
  echo TRANSFER_EXCLUSION=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo REALIZED_PNL_RISK_SMOKE=FAIL RC=!RC!
)
exit /b !RC!
