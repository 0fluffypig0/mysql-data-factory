@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo MySQL Data Factory - Offline Setup
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "ENV_FILE=%PROJECT_DIR%\env_export\mysql_factory_env.tar.gz"
set "TARGET_DIR=C:\tools\mysql_factory_env"
set "TARGET_PYTHON=%TARGET_DIR%\python.exe"
set "CONDA_UNPACK=%TARGET_DIR%\Scripts\conda-unpack.exe"

if not exist "%ENV_FILE%" (
    echo [ERROR] Offline environment package not found:
    echo         %ENV_FILE%
    echo.
    echo Please build it on the online machine first:
    echo   python scripts\build_offline_env.py
    exit /b 1
)

where tar >nul 2>nul
if errorlevel 1 (
    echo [ERROR] tar was not found on this machine.
    echo Please ensure Windows tar is available before running setup.
    exit /b 1
)

echo [1/4] Preparing target directory...
if not exist "%TARGET_DIR%" (
    mkdir "%TARGET_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create target directory:
        echo         %TARGET_DIR%
        exit /b 1
    )
)

echo.
echo [2/4] Extracting offline environment...
tar -xzf "%ENV_FILE%" -C "%TARGET_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to extract offline environment package.
    exit /b 1
)

echo.
echo [3/4] Running conda-unpack...
if exist "%CONDA_UNPACK%" (
    "%CONDA_UNPACK%"
    if errorlevel 1 (
        echo [ERROR] conda-unpack failed.
        exit /b 1
    )
) else (
    echo [WARNING] conda-unpack.exe not found. Continuing without it.
)

echo.
echo [4/4] Verifying python.exe...
if not exist "%TARGET_PYTHON%" (
    echo [ERROR] python.exe not found after extraction:
    echo         %TARGET_PYTHON%
    exit /b 1
)

"%TARGET_PYTHON%" --version
if errorlevel 1 (
    echo [ERROR] python.exe exists but could not run successfully.
    exit /b 1
)

echo.
echo ========================================
echo Offline environment is ready.
echo ========================================
echo Environment path: %TARGET_DIR%
echo Python: %TARGET_PYTHON%
echo.
echo Next steps:
echo   1. copy .env.example .env
echo   2. edit .env
echo   3. run bin\test_connection.bat
echo   4. run bin\export_sample.bat
