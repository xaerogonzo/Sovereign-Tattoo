@echo off
setlocal
set "dir=%~dp0"
set "py=python"

:: If a file was dragged, pass it through to the GUI for auto-load
if "%~1"=="" (
    %py% "%dir%sovereign_gui.py"
) else (
    %py% "%dir%sovereign_gui.py" "%~1"
)

:: If python isn't on PATH, give a clear error
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to launch. Ensure Python 3.10+ is installed and on PATH,
    echo         then run: pip install pywebview keyring
    pause
)
