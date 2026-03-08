@echo off
title Psimplicity - AI Script to Image Pipeline
color 0B

:: CRITICAL: Run from the folder where this .bat file lives
cd /d "%~dp0"

echo.
echo  ============================================
echo   Psimplicity  ⚡  AI Script to Image Pipeline
echo  ============================================
echo.
echo  Running from: %cd%
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed!
    echo.
    echo  Download it from: https://www.python.org/downloads/
    echo  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo  [OK] %%i found.

:: Check if .env exists
if exist ".env" goto skip_env_setup

echo.
echo  ============================================
echo   FIRST TIME SETUP - API KEY NEEDED
echo  ============================================
echo.

if exist ".env.example" (
    copy .env.example .env >nul
)

echo  You need a FREE Gemini API key:
echo.
echo  1. Open: https://aistudio.google.com/apikey
echo  2. Sign in with Google
echo  3. Click "Create API Key"
echo  4. Copy the key
echo.
echo  [IMPORTANT INSTRUCTION]
echo  Once the app opens in your browser, look for the "Configuration" 
echo  menu on the left side of the screen. Paste your key there and
echo  click "Save Configuration"!
echo.

set GEMINI_KEY=
set /p GEMINI_KEY="  Paste your API key here (or press Enter to skip): "

:: Write key to .env securely without fragile powershell string parsing
if not "%GEMINI_KEY%"=="" (
    echo.>> .env
    echo GEMINI_API_KEY=%GEMINI_KEY%>> .env
)

echo.
echo  [OK] API key saved to .env
echo.

:: Verify
type .env
echo.

:skip_env_setup

:: Install dependencies
echo  Installing packages... (this takes 1-2 min on first run)
echo.
python -m pip install -r requirements.txt
echo.

if errorlevel 1 (
    echo  [ERROR] Package install failed. Check the errors above.
    pause
    exit /b 1
)

echo.
echo  [OK] All packages installed!
echo.
echo  ============================================
echo   STARTING Psimplicity
echo  ============================================
echo.
echo  The browser will open automatically when ready.
echo  Keep this window open while using the app.
echo  Press Ctrl+C here to stop.
echo.

:: Let Streamlit run and automatically open the browser on an available port
python -m streamlit run app.py

pause
