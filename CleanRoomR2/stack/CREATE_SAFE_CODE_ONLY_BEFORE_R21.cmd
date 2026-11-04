@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "OUT=%~dp0..\WSRTD_SAFE_CODE_ONLY_BEFORE_R21.zip"
if exist "%OUT%" del /q "%OUT%"
where tar.exe >nul 2>nul || (
  echo SAFE_CODE_ONLY=FAIL_NO_TAR
  exit /b 1
)
tar.exe -a -c -f "%OUT%" --exclude=.venv --exclude=logs --exclude=runtime --exclude=__pycache__ --exclude=*.dll --exclude=*.zip *
if errorlevel 1 (
  echo SAFE_CODE_ONLY=FAIL_ARCHIVE
  exit /b 1
)
for %%I in ("%OUT%") do echo SAFE_CODE_ONLY_SIZE_BYTES=%%~zI
certutil -hashfile "%OUT%" SHA256
if errorlevel 1 exit /b 1
echo SAFE_CODE_ONLY=PASS
echo SAFE_CODE_ONLY_PATH=%OUT%
endlocal
