@echo off
setlocal
set PYTHONUTF8=1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-StarcupLive.ps1" %*
if errorlevel 1 (
  echo Starcup public live startup failed. Review the message above.
  pause
  exit /b 1
)
endlocal
