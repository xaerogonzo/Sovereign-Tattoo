@echo off
REM ============================================================
REM  install_tesseract.bat — double-click to install portable Tesseract
REM  into bin/tesseract/. Forwards any extra args to the Python script
REM  (e.g. --force, --remove).
REM ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"

REM Resolve the python launcher: prefer `py` (Python launcher for Windows),
REM fall back to plain `python` on PATH.
set "PY=py"
where py >nul 2>&1 || set "PY=python"

%PY% "%SCRIPT_DIR%install_tesseract.py" %*
set "RC=%ERRORLEVEL%"

REM Pause if launched by double-click (no console args, no parent console).
REM Detect double-click via empty CMDCMDLINE that doesn't contain /c.
echo.
if "%1"=="" (
    echo Press any key to close...
    pause >nul
)
exit /b %RC%
