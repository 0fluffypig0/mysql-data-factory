@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PYTHONIOENCODING=utf-8"

:: Try runtime (new 3.0 layout) first, then fallback to old C:\tools path
set "ENV_PYTHON=%PROJECT_DIR%\runtime\mysql_factory_env\python\python.exe"
if not exist "%ENV_PYTHON%" (
    set "ENV_PYTHON=C:\tools\mysql_factory_env\python.exe"
)

if not exist "%ENV_PYTHON%" (
    echo [ERROR] Offline Python environment not found.
    echo Please run: bin\setup_offline.bat
    exit /b 1
)

if exist "%PROJECT_DIR%\runtime\mysql_factory_env\python\tcl\tcl8.6" (
    set "TCL_LIBRARY=%PROJECT_DIR%\runtime\mysql_factory_env\python\tcl\tcl8.6"
)
if exist "%PROJECT_DIR%\runtime\mysql_factory_env\python\tcl\tk8.6" (
    set "TK_LIBRARY=%PROJECT_DIR%\runtime\mysql_factory_env\python\tcl\tk8.6"
)

cd /d "%PROJECT_DIR%"
"%ENV_PYTHON%" scripts\ui_app.py %*
