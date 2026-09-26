@echo off
setlocal
set ROOT=%~dp0..
set FIXTURE=%ROOT%\account\tests\fixtures\binance_usdm_account_v3.json
set OUTPUT=%ROOT%\runtime\account_risk_status.v1.json

python "%ROOT%\account\binance_usdm_readonly_gateway.py" --once --fixture "%FIXTURE%" --output "%OUTPUT%"
if errorlevel 1 (
  echo READONLY_ACCOUNT_FIXTURE=FAIL
  exit /b 1
)

echo READONLY_ACCOUNT_FIXTURE=PASS
echo OUTPUT=%OUTPUT%
exit /b 0
