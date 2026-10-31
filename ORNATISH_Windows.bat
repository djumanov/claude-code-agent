@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || where py >nul 2>nul || (
  echo Python topilmadi. https://www.python.org/downloads/ dan ornating ^("Add Python to PATH" belgisini qoying^) va qayta ishga tushiring.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1"
pause
