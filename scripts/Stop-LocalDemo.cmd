@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-LocalDemo.ps1" %*
if errorlevel 1 (
  echo Local demo stop failed. Review the message above.
  pause
  exit /b 1
)
endlocal
