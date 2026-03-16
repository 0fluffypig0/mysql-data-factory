@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ========================================
REM MySQL Data Factory - Jupyter Notebook 启动脚本
REM ========================================
REM 
REM 功能：启动 Jupyter Notebook 开发环境
REM 使用场景：离线环境部署完成后使用
REM 
REM 使用方法：
REM   双击此文件或从命令行运行
REM   bin\run_notebook.bat
REM 
REM 依赖：
REM   - 已运行 setup_offline.bat 完成环境部署
REM   - 环境路径：C:\tools\mysql_factory_env
REM 
REM ========================================

echo.
echo ========================================
echo   MySQL Data Factory
echo   Jupyter Notebook 启动器
echo ========================================
echo.

REM 设置路径
set "ENV_PYTHON=C:\tools\mysql_factory_env\python.exe"
set "ENV_JUPYTER=C:\tools\mysql_factory_env\Scripts\jupyter.exe"
set "PROJECT_DIR=%~dp0.."

REM 检查环境是否已部署
echo [检查] 验证离线环境...
if not exist "%ENV_PYTHON%" (
    echo.
    echo [错误] 未找到 Python 环境
    echo.
    echo 可能原因：
    echo   1. 尚未运行部署脚本
    echo   2. 环境路径不正确
    echo.
    echo 解决方法：
    echo   请先运行：bin\setup_offline.bat
    echo.
    echo 预期路径：%ENV_PYTHON%
    echo.
    pause
    exit /b 1
)

if not exist "%ENV_JUPYTER%" (
    echo.
    echo [错误] 未找到 Jupyter
    echo.
    echo 可能原因：
    echo   1. 环境未完整安装
    echo   2. Jupyter 未安装
    echo.
    echo 解决方法：
    echo   重新运行：bin\setup_offline.bat
    echo.
    pause
    exit /b 1
)

echo [✓] Python 环境已找到
echo [✓] Jupyter 已找到
echo.

REM 检查端口占用
set "NOTEBOOK_PORT=8888"
echo [检查] 检查端口 %NOTEBOOK_PORT%...
netstat -ano | findstr :%NOTEBOOK_PORT% >nul
if %errorlevel% equ 0 (
    echo [警告] 端口 %NOTEBOOK_PORT% 已被占用
    echo.
    echo 可能已有 Jupyter 在运行
    echo.
    choice /C YN /M "是否强制启动新实例（Y/N）"
    if errorlevel 2 (
        echo.
        echo 已取消启动
        pause
        exit /b 0
    )
    set "NOTEBOOK_PORT=8889"
    echo [信息] 使用备用端口：%NOTEBOOK_PORT%
)

echo.
echo [信息] 项目目录：%PROJECT_DIR%
echo.

REM 切换到项目目录
cd /d "%PROJECT_DIR%"

echo ========================================
echo   启动 Jupyter Notebook...
echo ========================================
echo.
echo 访问地址：http://localhost:%NOTEBOOK_PORT%
echo.
echo 提示：
echo   - 浏览器会自动打开
echo   - 如果没有自动打开，请手动访问上面的地址
echo   - 按 Ctrl+C 可以停止服务
echo.
echo ========================================
echo.

REM 启动 Jupyter Notebook
"%ENV_JUPYTER%" notebook --port %NOTEBOOK_PORT% --notebook-dir="%PROJECT_DIR%"

REM 如果 Jupyter 退出
echo.
echo ========================================
echo   Jupyter Notebook 已关闭
echo ========================================
echo.
pause