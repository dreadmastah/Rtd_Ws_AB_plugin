@echo off
setlocal
where cl >nul 2>nul || (
  echo ERROR: Run from an x64 Visual Studio Developer Command Prompt.
  exit /b 1
)
cl /nologo /c /O2 /Ob0 /GS- /GR- /Zl /Fowsrtd_compat.obj wsrtd_compat.cpp || exit /b 1
link /nologo /dll /noentry /machine:x64 /nodefaultlib /def:wsrtd_compat.def ^
  /out:WsRTD_Compat_3.06.26_R2_x64.dll wsrtd_compat.obj ^
  kernel32.lib user32.lib advapi32.lib ws2_32.lib msvcrt.lib || exit /b 1
echo.
echo Build complete: WsRTD_Compat_3.06.26_R2_x64.dll
certutil -hashfile WsRTD_Compat_3.06.26_R2_x64.dll SHA256
endlocal
