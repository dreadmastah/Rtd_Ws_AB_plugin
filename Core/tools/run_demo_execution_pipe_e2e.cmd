@echo off
setlocal EnableExtensions

set ROOT=%~dp0..
set BUILD=%ROOT%\..\build\core\Release
set HOST=%BUILD%\astu_demo_execution_pipe_host.exe
set CLIENT=%BUILD%\astu_demo_execution_pipe_e2e.exe
set SECURITY=%BUILD%\astu_named_pipe_security_tests.exe
set JOURNAL=%ROOT%\..\build\core\demo_pipe_e2e_journal.jsonl
set CONVERGENCE=%ROOT%\..\build\core\demo_pipe_e2e_convergence.json

if not exist "%HOST%" (
  echo ERROR: missing %HOST%
  exit /b 2
)
if not exist "%CLIENT%" (
  echo ERROR: missing %CLIENT%
  exit /b 2
)
if not exist "%SECURITY%" (
  echo ERROR: missing %SECURITY%
  exit /b 2
)

set ASTU_DEMO_EXECUTION_CAPABILITY_TOKEN=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

"%SECURITY%"
if errorlevel 1 exit /b %ERRORLEVEL%

call :run_case valid fresh
if errorlevel 1 exit /b %ERRORLEVEL%

call :run_case bad-source fresh
if errorlevel 1 exit /b %ERRORLEVEL%

call :run_case bad-capability fresh
if errorlevel 1 exit /b %ERRORLEVEL%

call :run_case stale-convergence stale
if errorlevel 1 exit /b %ERRORLEVEL%

echo DEMO_PIPE_E2E=PASS
echo DEMO_PIPE_CURRENT_USER_DACL=PASS
echo DEMO_PIPE_CORRELATION=PASS
echo DEMO_PIPE_SOURCE_GUARD=PASS
echo DEMO_PIPE_CAPABILITY_GUARD=PASS
echo DEMO_PIPE_CONVERGENCE_GUARD=PASS
echo DEMO_PIPE_NO_SUBMISSION=PASS
exit /b 0

:run_case
set CASE=%~1
set FRESHNESS=%~2
del /q "%JOURNAL%" >nul 2>nul
del /q "%CONVERGENCE%" >nul 2>nul

if /I "%FRESHNESS%"=="stale" (
  "%CLIENT%" --prepare --stale --journal "%JOURNAL%" --convergence "%CONVERGENCE%"
) else (
  "%CLIENT%" --prepare --journal "%JOURNAL%" --convergence "%CONVERGENCE%"
)
if errorlevel 1 exit /b %ERRORLEVEL%

start "ASTU Demo Admission Host %CASE%" /b "%HOST%" --once --journal "%JOURNAL%" --convergence-state "%CONVERGENCE%"
ping -n 2 127.0.0.1 >nul

"%CLIENT%" --case "%CASE%" --journal "%JOURNAL%" --convergence "%CONVERGENCE%"
set RC=%ERRORLEVEL%

taskkill /IM astu_demo_execution_pipe_host.exe /F >nul 2>nul
ping -n 2 127.0.0.1 >nul

exit /b %RC%
