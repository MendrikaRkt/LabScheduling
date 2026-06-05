@echo off
REM ============================================================
REM  build.bat - One-click Windows build for Lab Scheduling
REM  Produces:  Output\LabScheduling_Setup_v1.0.0.exe
REM
REM  Prerequisites (install once):
REM    1. Python 3.11 or 3.12 (64-bit)  -> https://www.python.org/downloads/
REM       (tick "Add python.exe to PATH" during install)
REM    2. Inno Setup 6                  -> https://jrsoftware.org/isdl.php
REM
REM  Then just double-click this file (or run it in a terminal).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Stamp the build version (read by the in-app updater). Edit APP_VERSION
REM here AND in installer.iss (MyAppVersion) when you cut a new release.
set "APP_VERSION=1.0.0"
echo %APP_VERSION%> VERSION.txt
echo Building version %APP_VERSION%

echo.
echo === [1/4] Creating / activating virtual environment ===
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo.
echo === [2/4] Installing dependencies ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo === [3/4] Building the app with PyInstaller ===
pyinstaller LabScheduling.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See the log above.
    pause
    exit /b 1
)

echo.
echo === [4/4] Building the Windows installer with Inno Setup ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "!ISCC!" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "!ISCC!" (
    echo.
    echo [WARN] Inno Setup not found. The standalone app is ready in:
    echo        dist\LabScheduling\LabScheduling.exe
    echo        Install Inno Setup 6 to also produce the single-file installer.
    pause
    exit /b 0
)
"!ISCC!" installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Installer : Output\LabScheduling_Setup_v1.0.0.exe
echo  Portable  : dist\LabScheduling\LabScheduling.exe
echo ============================================================
pause