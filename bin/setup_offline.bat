@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo MySQL Data Factory 3.00 - Offline Setup
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "ENV_FILE=%PROJECT_DIR%\env_export\mysql_factory_env.zip"
set "TARGET_DIR=%PROJECT_DIR%\runtime"
set "TARGET_ENV_DIR=%TARGET_DIR%\mysql_factory_env"
set "TARGET_PYTHON=%TARGET_ENV_DIR%\python\python.exe"
set "VENDOR_DIR=%TARGET_ENV_DIR%\vendor"
set "TCL_LIBRARY=%TARGET_ENV_DIR%\python\tcl\tcl8.6"
set "TK_LIBRARY=%TARGET_ENV_DIR%\python\tcl\tk8.6"

if not exist "%ENV_FILE%" (
    echo [ERROR] Offline environment package not found:
    echo         %ENV_FILE%
    echo.
    echo Please build it on the online machine first:
    echo   python scripts\build_offline_env.py
    exit /b 1
)

echo [1/3] Preparing offline environment...
if exist "%TARGET_PYTHON%" (
    echo       Existing runtime detected. Reusing current extracted files.
    echo       Delete runtime\mysql_factory_env manually if you need a full reinstall.
) else (
    echo       Extracting offline environment...
    mkdir "%TARGET_DIR%" 2>nul
    tar -xf "%ENV_FILE%" -C "%TARGET_DIR%"
    if errorlevel 1 (
        echo [WARN] tar extraction failed. Falling back to PowerShell Expand-Archive...
        powershell -Command "Expand-Archive -Path '%ENV_FILE%' -DestinationPath '%TARGET_DIR%' -Force"
        if errorlevel 1 (
            echo [ERROR] Extraction failed.
            exit /b 1
        )
    )
)

echo.
echo [2/3] Installing dependencies from vendor...
if not exist "%TARGET_PYTHON%" (
    echo [ERROR] python.exe not found after extraction:
    echo         %TARGET_PYTHON%
    exit /b 1
)

"%TARGET_PYTHON%" -m pip install --no-index --find-links="%VENDOR_DIR%" -r "%PROJECT_DIR%\requirements.txt" --no-warn-script-location
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
)

echo.
echo [3/3] Verifying python.exe...
"%TARGET_PYTHON%" --version
if errorlevel 1 (
    echo [ERROR] python.exe exists but could not run successfully.
    exit /b 1
)

"%TARGET_PYTHON%" -c "import pymysql; print('pymysql OK')"
if errorlevel 1 (
    echo [ERROR] pymysql import check failed.
    exit /b 1
)

"%TARGET_PYTHON%" -c "import tkinter as tk; print('tkinter OK'); print(tk.Tcl().eval('info library'))"
if errorlevel 1 (
    echo [ERROR] tkinter import check failed.
    exit /b 1
)

echo.
echo ========================================
echo Offline environment is ready!
echo ========================================
echo Environment: %TARGET_ENV_DIR%
echo Python:      %TARGET_PYTHON%
echo TCL_LIBRARY: %TCL_LIBRARY%
echo TK_LIBRARY:  %TK_LIBRARY%
echo.
echo Next steps:
echo   1. copy .env.example .env
echo   2. edit .env with your database credentials
echo   3. run bin\test_connection.bat
echo   4. run bin\run_gui.bat
