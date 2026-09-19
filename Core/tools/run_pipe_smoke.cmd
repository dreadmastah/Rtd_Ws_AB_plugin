@echo off
setlocal
set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  echo Build first:
  echo   cmake -S Core -B build/core
  echo   cmake --build build/core --config Release
  exit /b 2
)

if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)

start "ASTU Execution Simulation Host" /b "%HOST%" --synthetic
timeout /t 1 /nobreak >nul
"%CLIENT%"
set RC=%ERRORLEVEL%

if %RC% EQU 0 (
  echo PIPE_SMOKE=PASS
) else (
  echo PIPE_SMOKE=FAIL RC=%RC%
)

taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul
exit /b %RC%
