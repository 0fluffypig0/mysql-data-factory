@echo off
chcp 65001 >nul
setlocal

set "ENV_PYTHON=C:\tools\mysql_factory_env\python.exe"
set "PROJECT_DIR=%~dp0.."
set "PYTHONIOENCODING=utf-8"

if not exist "%ENV_PYTHON%" (
    echo [ERROR] Offline Python environment not found.
    echo Please run: bin\setup_offline.bat
    exit /b 1
)

cd /d "%PROJECT_DIR%"
"%ENV_PYTHON%" scripts\insert_csv.py %*
