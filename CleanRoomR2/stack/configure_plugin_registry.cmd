@echo off
setlocal EnableExtensions
set "DBNAME=%~1"
if "%DBNAME%"=="" set "DBNAME=Data"
set "PORT=%~2"
if "%PORT%"=="" set "PORT=10101"
set "KEY=HKCU\SOFTWARE\TJP\WsRtD\%DBNAME%"

echo Configuring WSRTD registry for AmiBroker DB name: %DBNAME% on port %PORT%
reg add "%KEY%" /v Server /t REG_SZ /d 127.0.0.1 /f >nul || exit /b 1
reg add "%KEY%" /v Port /t REG_DWORD /d %PORT% /f >nul || exit /b 1
reg add "%KEY%" /v RefreshInterval /t REG_DWORD /d 250 /f >nul || exit /b 1
reg add "%KEY%" /v AuthCode /t REG_SZ /d "" /f >nul || exit /b 1
reg add "%KEY%" /v AutoAddSymbols /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "%KEY%" /v SymbolLimit /t REG_DWORD /d 1000 /f >nul || exit /b 1
reg add "%KEY%" /v EODRetention /t REG_DWORD /d 300 /f >nul || exit /b 1
reg add "%KEY%" /v IntradayRetention /t REG_DWORD /d 1500 /f >nul || exit /b 1
reg add "%KEY%" /v QuoteLimit /t REG_DWORD /d 1800 /f >nul || exit /b 1
reg add "%KEY%" /v CPing /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "%KEY%" /v AutoSavePluginDB /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "%KEY%" /v AutoSavePendingBF /t REG_DWORD /d 0 /f >nul || exit /b 1
reg add "%KEY%" /v AutoDelLRU /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "%KEY%" /v EODMixedMode /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "%KEY%" /v MergePartialBackfill /t REG_DWORD /d 1 /f >nul || exit /b 1

echo WSRTD_REGISTRY_CONFIG=PASS
reg query "%KEY%"
exit /b 0
