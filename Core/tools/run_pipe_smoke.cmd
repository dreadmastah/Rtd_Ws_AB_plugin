@echo off
setlocal
set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core
set HOST=%BUILD%\Release\astu_execution_pipe_host.exe
set CLIENT=%BUILD%\Release\astu_trade_pipe_smoke.exe
set JOURNAL=%BUILD%\pipe_smoke_execution_journal.jsonl

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

del /q "%JOURNAL%" >nul 2>nul

start "ASTU Execution Simulation Host" /b "%HOST%" --synthetic --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%"
set RC=%ERRORLEVEL%
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if not %RC% EQU 0 (
  echo PIPE_SMOKE=FAIL RC=%RC%
  exit /b %RC%
)

ping -n 2 127.0.0.1 >nul
start "ASTU Execution Simulation Host Replay" /b "%HOST%" --synthetic --journal "%JOURNAL%"
ping -n 2 127.0.0.1 >nul
"%CLIENT%" --expect-duplicate
set REPLAY_RC=%ERRORLEVEL%
taskkill /IM astu_execution_pipe_host.exe /F >nul 2>nul

if %REPLAY_RC% EQU 0 (
  echo PIPE_SMOKE=PASS
  echo PIPE_DURABLE_REPLAY_GUARD=PASS
) else (
  echo PIPE_SMOKE=FAIL REPLAY_RC=%REPLAY_RC%
)

exit /b %REPLAY_RC%
