@echo off
title Psimplicity Frontend - Alchemical Visuals
color 0E

cd /d "%~dp0\web"

:: Check if node_modules exists, if not run install
if not exist "node_modules" (
    echo [!] Installing dependencies - first run only...
    call npm install
)

:: Start Dev Server
echo.
echo [!] Starting Psimplicity Frontend...
echo.
call npm run dev

pause
