@echo off
title ATHENA Desktop Launcher
cd /d "%~dp0"
echo ===================================================
echo             ATHENA ACCA ENGINE LAUNCHER            
echo ===================================================
echo Starting local backend server and desktop interface...
.\.venv\Scripts\python run_desktop.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start ATHENA Desktop App.
    pause
)
