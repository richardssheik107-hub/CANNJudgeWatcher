@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-StarcupLive.ps1" %*
if errorlevel 1 (
  echo Starcup public live stop failed. Review the message above.
  pause
  exit /b 1
)
endlocal
