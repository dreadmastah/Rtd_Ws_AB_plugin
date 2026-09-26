@echo off
setlocal

set ROOT=%~dp0..
set DLL=%ROOT%\..\build\core\Release\AstuTrade.dll
set TARGET=%ProgramFiles%\AmiBroker\Plugins

if not "%~1"=="" set TARGET=%~1

if not exist "%DLL%" (
  echo ERROR: AstuTrade.dll not found:
  echo   %DLL%
  echo Build first:
  echo   cmake -S Core -B build/core
  echo   cmake --build build/core --config Release
  exit /b 2
)

if not exist "%TARGET%" (
  echo ERROR: AmiBroker Plugins directory not found:
  echo   %TARGET%
  echo Pass the actual Plugins directory as the first argument.
  exit /b 3
)

if exist "%TARGET%\AstuTrade.dll" (
  copy /y "%TARGET%\AstuTrade.dll" "%TARGET%\AstuTrade.dll.bak" >nul
  if errorlevel 1 (
    echo ERROR: failed to create AstuTrade.dll.bak
    exit /b 4
  )
)

copy /y "%DLL%" "%TARGET%\AstuTrade.dll" >nul
if errorlevel 1 (
  echo ERROR: failed to copy AstuTrade.dll
  exit /b 5
)

echo ASTU_TRADE_PLUGIN_INSTALL=PASS
echo SOURCE=%DLL%
echo TARGET=%TARGET%\AstuTrade.dll
echo.
echo Set ASTU_STATUS_DIR before launching AmiBroker.
echo Example:
echo   set ASTU_STATUS_DIR=D:\path\to\CleanRoomR2\stack\runtime\autotrader_status
echo.
echo The current plugin is SIMULATION ONLY.
exit /b 0
