@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set RECON=%BUILD%\Release\astu_reconciliation_pipe_smoke.exe
set JOURNAL=%BUILD%\projected_risk_limits_journal.jsonl
set STATUS=%BUILD%\projected_risk_limits_status.v1.json
set FIRST=%BUILD%\projected_risk_limits_first.out
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

rem Phase A: pending entry/scale-in reservation count.
start "ASTU Projected Risk Pending Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 1 ^
  --max-symbol-notional 0 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id PENDING-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED > "%FIRST%" 2>&1
if errorlevel 1 (
  type "%FIRST%"
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_FIRST_ACCEPT
  set RC=3
  goto cleanup
)
type "%FIRST%"

for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulationOrderId=" "%FIRST%"') do set ORDER_ID=%%A
for /f "tokens=2 delims==" %%A in ('findstr /B /C:"simulatedQuantity=" "%FIRST%"') do set ORDER_QTY=%%A
if "!ORDER_ID!"=="" (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL ORDER_ID_MISSING
  set RC=4
  goto cleanup
)
if "!ORDER_QTY!"=="" (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL ORDER_QTY_MISSING
  set RC=5
  goto cleanup
)

"%CLIENT%" --case-id PENDING-2 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_LIMIT_NOT_ENFORCED
  set RC=6
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
powershell.exe -NoProfile -Command "$o=$null; foreach($ms in 0,100,200,500){ if($ms){Start-Sleep -Milliseconds $ms}; try{$o=Get-Content -LiteralPath '%STATUS%' -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop; break}catch{}}; if($null -eq $o){throw 'status read failed'}; if($o.maxPendingEntryScaleInReservations -ne 1 -or $o.maxSymbolNotional -ne 0 -or $o.activeExposureReservations -ne 1 -or $o.reservedPositionSlots -ne 1 -or $o.orderRoutingEnabled -ne $false){throw 'pending status assertion failed'}; Write-Output 'PROJECTED_PENDING_LIMIT=PASS'"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_STATUS
  set RC=7
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

start "ASTU Projected Risk Pending Restart Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 1 ^
  --max-symbol-notional 0 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 3 127.0.0.1 >nul

"%CLIENT%" --case-id PENDING-3 --symbol ETHUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_RESTART_NOT_ENFORCED
  set RC=8
  goto cleanup
)

"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-UNKNOWN --event MARK_UNKNOWN --cumulative-filled 0 --detail "pending limit release unknown"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_MARK_UNKNOWN
  set RC=9
  goto cleanup
)
"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-WORKING --event WORKING --cumulative-filled 0 --detail "pending limit release working"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_WORKING
  set RC=10
  goto cleanup
)
"%RECON%" --order-id "!ORDER_ID!" --event-id LIMIT-FILLED --event FILLED --cumulative-filled "!ORDER_QTY!" --detail "pending limit release filled"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_FILLED
  set RC=11
  goto cleanup
)

"%CLIENT%" --case-id PENDING-4 --symbol ETHUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL PENDING_HEADROOM_NOT_RESTORED
  set RC=12
  goto cleanup
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

rem Phase B: per-symbol projected notional.
del /q "%JOURNAL%" >nul 2>nul
del /q "%STATUS%" >nul 2>nul

start "ASTU Projected Risk Symbol Host" /b "%HOST%" ^
  --synthetic ^
  --synthetic-max-gross-notional 100000 ^
  --synthetic-max-open-positions 10 ^
  --max-pending-entry-scale-in-reservations 0 ^
  --max-symbol-notional 10 ^
  --journal "%JOURNAL%" ^
  --execution-status-file "%STATUS%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case-id SYMBOL-1 --symbol BTCUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_FIRST_ACCEPT
  set RC=13
  goto cleanup
)

"%CLIENT%" --case-id SYMBOL-2 --symbol BTCUSDT --expect RISK_BLOCKED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_LIMIT_NOT_ENFORCED
  set RC=14
  goto cleanup
)

"%CLIENT%" --case-id SYMBOL-3 --symbol ETHUSDT --expect ORDER_ROUTING_DISABLED
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_ISOLATION
  set RC=15
  goto cleanup
)

ping -n 2 127.0.0.1 >nul
powershell.exe -NoProfile -Command "$o=$null; foreach($ms in 0,100,200,500){ if($ms){Start-Sleep -Milliseconds $ms}; try{$o=Get-Content -LiteralPath '%STATUS%' -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop; break}catch{}}; if($null -eq $o){throw 'status read failed'}; if($o.maxPendingEntryScaleInReservations -ne 0 -or [math]::Abs([double]$o.maxSymbolNotional-10.0) -ge 1e-12 -or $o.activeExposureReservations -ne 2 -or [math]::Abs([double]$o.reservedGrossNotional-20.0) -ge 1e-9 -or $o.reservedPositionSlots -ne 2 -or $o.orderRoutingEnabled -ne $false){throw 'symbol status assertion failed'}; Write-Output 'PROJECTED_SYMBOL_LIMIT=PASS'"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL SYMBOL_STATUS
  set RC=16
  goto cleanup
)

powershell.exe -NoProfile -Command "$rows=$null; foreach($ms in 0,100,200,500){ if($ms){Start-Sleep -Milliseconds $ms}; try{$rows=@(Get-Content -LiteralPath '%JOURNAL%' -ErrorAction Stop | Where-Object {$_.Trim()} | ForEach-Object {$_ | ConvertFrom-Json -ErrorAction Stop}); break}catch{}}; if($null -eq $rows){throw 'journal read failed'}; $creates=@($rows | Where-Object {$_.eventType -eq 'EXPOSURE_RESERVATION_CREATED'}); $symbols=@($creates.symbol | Sort-Object -Unique); if($creates.Count -ne 2 -or ($symbols -join ',') -ne 'BTCUSDT,ETHUSDT' -or @($rows | Where-Object {$_.toState -eq 'SUBMITTING'}).Count -ne 0 -or @($rows | Where-Object {$_.exchangeSubmissionAttempted -eq $true}).Count -ne 0){throw 'journal assertion failed'}; Write-Output 'PROJECTED_RISK_LIMITS_JOURNAL=PASS'"
if errorlevel 1 (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL JOURNAL
  set RC=17
  goto cleanup
)

:cleanup
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if !RC! EQU 0 (
  echo PROJECTED_RISK_LIMITS_SMOKE=PASS
  echo PENDING_RESERVATION_LIMIT=PASS
  echo PENDING_LIMIT_RESTART=PASS
  echo TERMINAL_RELEASE_RESTORES_SLOT=PASS
  echo PER_SYMBOL_PROJECTED_NOTIONAL=PASS
  echo SYMBOL_ISOLATION=PASS
  echo ORDER_ROUTING_ENABLED=false
) else (
  echo PROJECTED_RISK_LIMITS_SMOKE=FAIL RC=!RC!
)

exit /b !RC!
