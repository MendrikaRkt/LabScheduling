@echo off
REM ============================================================
REM  build_patch.bat - Create a distributable Python patch .zip
REM
REM  A patch updates the app's .py code WITHOUT a full rebuild.
REM  The user applies it from the app's "Updates" page; the patched
REM  modules shadow the bundled ones on the next launch.
REM
REM  USAGE:
REM    build_patch.bat 1.0.1 "Fix S2 export and logo" app.py excel_export.py
REM
REM  ARGS:
REM    %1            = new version (e.g. 1.0.1)
REM    %2            = quoted notes shown in the app
REM    %3 %4 ...     = the .py files to include in the patch
REM
REM  OUTPUT:
REM    patches_out\LabScheduling_patch_v<version>.zip
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if "%~1"=="" (
  echo [ERROR] Missing version. Example:
  echo    build_patch.bat 1.0.1 "Fix S2 export" app.py excel_export.py
  exit /b 1
)
if "%~2"=="" (
  echo [ERROR] Missing notes string ^(quote it^).
  exit /b 1
)

set "VER=%~1"
set "NOTES=%~2"

REM Collect file args (everything from %3 onward)
set "FILES="
shift
shift
:collect
if "%~1"=="" goto done
set "FILES=!FILES! %1"
shift
goto collect
:done

if "!FILES!"=="" (
  echo [ERROR] No .py files specified.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [WARN] .venv not found; using system python.
  set "PY=python"
) else (
  set "PY=.venv\Scripts\python.exe"
)

if not exist "patches_out" mkdir patches_out
set "OUT=patches_out\LabScheduling_patch_v%VER%.zip"

%PY% -c "import update_manager as u, sys; r=u.build_patch(sys.argv[1], sys.argv[3:], sys.argv[2], notes=sys.argv[2]); print(r)" "%VER%" "%OUT%" !FILES!

REM The line above passes notes positionally; call the explicit form instead:
%PY% -c "import update_manager as u, sys; files=sys.argv[3:]; r=u.build_patch(sys.argv[1], files, sys.argv[2], notes='%NOTES%', min_app='1.0.0'); print('OK' if r['ok'] else 'FAIL: '+str(r.get('error')))" "%VER%" "%OUT%" !FILES!

echo.
echo Patch written to: %OUT%
echo Give that .zip to users; they apply it from the app's Updates page.
pause