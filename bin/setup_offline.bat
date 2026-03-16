@echo off
chcp 65001 >nul
echo ========================================
echo MySQL Data Factory - 离线环境部署
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set ENV_EXPORT_DIR=%PROJECT_DIR%\env_export
set TARGET_DIR=C:\tools\mysql_factory_env
set ENV_FILE=%ENV_EXPORT_DIR%\mysql_factory_env.tar.gz

echo [检查] 检查离线环境包...
if not exist "%ENV_FILE%" (
    echo [错误] 未找到离线环境包: %ENV_FILE%
    echo.
    echo 请先运行以下命令生成离线环境:
    echo   python scripts\create_offline_env.py
    echo.
    pause
    exit /b 1
)

echo [信息] 找到离线环境包
echo   %ENV_FILE%
echo.

echo [1/3] 创建环境目录...
if not exist "%TARGET_DIR%" (
    mkdir "%TARGET_DIR%"
    echo   创建目录: %TARGET_DIR%
)

echo.
echo [2/3] 解压环境包...
echo   目标目录: %TARGET_DIR%
tar -xzf "%ENV_FILE%" -C "%TARGET_DIR%"
if %errorlevel% neq 0 (
    echo [错误] 解压失败
    pause
    exit /b 1
)

echo.
echo [3/3] 修复路径...
if exist "%TARGET_DIR%\Scripts\conda-unpack.exe" (
    "%TARGET_DIR%\Scripts\conda-unpack.exe"
    echo   ✓ 路径修复完成
) else (
    echo [警告] 未找到 conda-unpack.exe
    echo   可能需要手动修复路径
)

echo.
echo ========================================
echo ✓ 离线环境部署完成！
echo ========================================
echo.
echo 环境路径: %TARGET_DIR%
echo Python: %TARGET_DIR%\python.exe
echo.
echo 下一步:
echo   1. 复制 .env.example 为 .env
echo   2. 编辑 .env 配置数据库信息
echo   3. 运行 bin\run_notebook.bat
echo.
pause