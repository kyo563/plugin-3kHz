@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup-desktop.ps1 first. See docs/WINDOWS_DESKTOP.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" desktop_entry.py %*
