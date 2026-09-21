@echo off
setlocal
set "DLL=WsRTD_Compat_3.06.26_R2_x64.dll"
if not exist "%DLL%" (echo VERIFY=FAIL_MISSING_DLL&exit /b 1)
certutil -hashfile "%DLL%" SHA256
where dumpbin >nul 2>nul && dumpbin /headers /exports "%DLL%"
echo VERIFY_PREBUILT=STATIC_ONLY_RUNTIME_AMIBROKER_STILL_REQUIRED
endlocal
