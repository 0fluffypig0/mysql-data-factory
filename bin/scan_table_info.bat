@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0.."
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

cd /d "%PROJECT_DIR%"
"%ENV_PYTHON%" scripts\scan_table_info.py %*
