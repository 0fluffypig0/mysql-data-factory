@echo off
chcp 65001 >nul

REM ========================================
REM MySQL Data Factory - 查询脚本
REM ========================================

echo.
echo ========================================
echo   MySQL Data Factory - 数据库查询
echo ========================================
echo.

set "ENV_PYTHON=C:\tools\mysql_factory_env\python.exe"
set "PROJECT_DIR=%~dp0.."

if not exist "%ENV_PYTHON%" (
    echo [错误] 未找到 Python 环境
    echo 请先运行：bin\setup_offline.bat
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

REM 运行查询脚本
"%ENV_PYTHON%" scripts\run_query.py

echo.
pause