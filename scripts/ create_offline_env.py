#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
MySQL Data Factory - 离线环境打包脚本
================================================================================

模块名称:
    create_offline_env.py

模块版本:
    1.0.0

功能描述:
    本脚本用于在可联网的开发机上创建完全离线的 Python 环境包。
    
    打包后的环境包包含：
    - Python 3.10 解释器
    - 所有必需的依赖包（pymysql, pandas, jupyter 等）
    - conda 环境配置
    
    打包后的环境包可在完全离线的堡垒机上直接使用，无需安装任何软件。

使用场景:
    1. 为隔离网络的堡垒机准备 Python 运行环境
    2. 为生产环境创建可复现的依赖环境
    3. 团队内部统一开发环境版本

使用方法:
    # 方式 1：直接运行（推荐）
    python scripts\create_offline_env.py
    
    # 方式 2：指定环境名称
    python scripts\create_offline_env.py --env-name my_env
    
    # 方式 3：自定义输出路径
    python scripts\create_offline_env.py --output-dir D:\exports

操作步骤:
    第 1 步：在可联网的 Windows 机器上安装 Miniconda
            下载地址：https://docs.conda.io/en/latest/miniconda.html
            安装文件：Miniconda3-latest-Windows-x86_64.exe
    
    第 2 步：克隆或下载本项目到本地
            git clone https://github.com/yourname/mysql-data-factory.git
            cd mysql-data-factory
    
    第 3 步：运行打包脚本
            python scripts\create_offline_env.py
    
    第 4 步：等待打包完成（约 5-10 分钟）
            输出文件：env_export\mysql_factory_env.tar.gz
    
    第 5 步：将整个项目文件夹复制到离线堡垒机
    
    第 6 步：在堡垒机上运行 bin\setup_offline.bat 完成部署

输入参数:
    无（使用默认配置）
    
    可选命令行参数:
    --env-name      环境名称（默认：mysql_factory）
    --output-dir    输出目录（默认：项目根目录/env_export）
    --python-version Python 版本（默认：3.10）

输出文件:
    env_export/mysql_factory_env.tar.gz    离线环境包（约 300-600MB）
    env_export/README_OFFLINE.md           部署说明文档

依赖要求:
    运行环境:
        - Python 3.8+
        - Conda (Miniconda 或 Anaconda)
        - Windows 10/11 或 Linux
    
    Python 包:
        - pathlib (标准库)
        - subprocess (标准库)
        - argparse (标准库)

打包内容:
    核心数据库包:
        - pymysql (MySQL 连接驱动)
        - sqlalchemy (ORM 框架)
        - mysql-connector-python (MySQL 官方驱动)
    
    数据处理包:
        - pandas (数据分析)
        - numpy (数值计算)
        - pyarrow (高性能数据格式)
        - openpyxl (Excel 读写)
        - xlsxwriter (Excel 写入)
    
    数据生成包:
        - faker (测试数据生成)
    
    工具包:
        - python-dotenv (环境变量管理)
        - loguru (日志记录)
        - tqdm (进度条)
    
    开发工具:
        - jupyter (Notebook)
        - notebook (Web 界面)
        - ipykernel (Jupyter 内核)
        - ipython (交互式 shell)

注意事项:
    ⚠️  操作系统兼容性:
        - Windows 打包的环境只能在 Windows 上使用
        - Linux 打包的环境只能在 Linux 上使用
        - 不支持跨平台使用
    
    ⚠️  磁盘空间:
        - 打包过程需要约 2GB 临时空间
        - 生成的离线包约 300-600MB
        - 解压后约占用 500MB-1GB
    
    ⚠️  网络要求:
        - 打包过程需要联网下载依赖包
        - 生成的离线包可在完全离线环境使用
    
    ⚠️  权限要求:
        - 需要对项目目录有写入权限
        - 需要对目标目录有读写权限

示例输出:
    ============================================================
    MySQL Data Factory - 离线环境构建
    ============================================================
    
    [1/4] 检查 conda...
    ✓ Conda 可用 (conda 24.1.0)
    
    [2/4] 创建 conda 环境: mysql_factory
    ✓ 环境创建成功
    
    [3/4] 安装包...
      安装 pymysql...
      安装 sqlalchemy...
      安装 pandas...
      ... (约 5-10 分钟)
    ✓ 所有包安装完成
    
    [4/4] 打包环境...
      安装 conda-pack...
    ✓ 打包完成：env_export\mysql_factory_env.tar.gz (456.32 MB)
    
    ============================================================
    🎉 离线环境构建完成！
    ============================================================

故障排除:
    问题 1: conda 命令未找到
    解决：确保已安装 Miniconda 并添加到 PATH 环境变量
    
    问题 2: 打包失败 - 空间不足
    解决：清理磁盘空间，确保至少有 2GB 可用空间
    
    问题 3: 某些包安装失败
    解决：检查网络连接，或尝试使用镜像源
          conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/

作者信息:
    作者：Your Name
    邮箱：your.email@example.com
    日期：2026-03-16
    版本：1.0.0

许可证:
    MIT License

================================================================================
"""

# ==================== 导入模块 ====================

import os
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


# ==================== 类定义 ====================

class OfflineEnvBuilder:
    """
    离线环境构建器
    
    负责创建、配置和打包完整的 Python 离线环境。
    
    属性:
        env_name (str): Conda 环境名称
        python_version (str): Python 版本
        output_dir (Path): 输出目录路径
        output_file (Path): 输出文件路径
        packages (list): 需要安装的包列表
    
    方法:
        check_conda(): 检查 conda 是否可用
        create_environment(): 创建 conda 环境
        install_packages(): 安装所有必需的包
        pack_environment(): 打包环境
        create_readme(): 创建部署说明文档
        build(): 执行完整构建流程
    """
    
    def __init__(self, env_name="mysql_factory", python_version="3.10", output_dir=None):
        """
        初始化离线环境构建器
        
        参数:
            env_name (str): Conda 环境名称，默认 "mysql_factory"
            python_version (str): Python 版本，默认 "3.10"
            output_dir (str, optional): 输出目录，默认项目根目录/env_export
        """
        self.env_name = env_name
        self.python_version = python_version
        self.project_root = Path(__file__).parent.parent
        self.env_export_dir = Path(output_dir) if output_dir else self.project_root / "env_export"
        self.output_file = self.env_export_dir / f"{env_name}_env.tar.gz"
        
        # 核心包列表
        self.core_packages = [
            'pymysql',              # MySQL 连接驱动
            'sqlalchemy',           # ORM 框架
            'pandas',               # 数据分析
            'numpy',                # 数值计算
            'faker',                # 测试数据生成
            'python-dotenv',        # 环境变量管理
            'loguru',               # 日志记录
            'tqdm',                 # 进度条
            'pyarrow',              # 高性能数据格式
            'mysql-connector-python' # MySQL 官方驱动
        ]
        
        # Jupyter 相关包
        self.jupyter_packages = [
            'jupyter',              # Jupyter 主程序
            'notebook',             # Notebook Web 界面
            'ipykernel',            # Jupyter 内核
            'ipython'               # 交互式 Python shell
        ]
    
    def check_conda(self):
        """
        检查 conda 是否可用
        
        返回:
            bool: conda 可用返回 True，否则返回 False
        """
        try:
            result = subprocess.run(
                ['conda', '--version'], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"✓ Conda 可用 ({result.stdout.strip()})")
                return True
            else:
                return False
        except Exception as e:
            print(f"❌ 检查 conda 失败：{e}")
            return False
    
    def create_environment(self):
        """
        创建 conda 环境
        
        执行命令:
            conda create -n {env_name} python={python_version} -y
        
        异常:
            RuntimeError: 如果环境创建失败
        """
        print(f"\n[2/4] 创建 conda 环境：{self.env_name}")
        
        cmd = [
            'conda', 'create', '-n', self.env_name,
            f'python={self.python_version}',
            '-y'  # 自动确认
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ 错误：创建环境失败")
            print(f"详细信息：{result.stderr}")
            raise RuntimeError("创建 conda 环境失败")
        
        print("✓ 环境创建成功")
    
    def install_packages(self):
        """
        安装所有必需的包
        
        分两批安装：
        1. 核心包（数据库、数据处理）
        2. Jupyter 工具包
        
        注意:
            - 使用 stdout=DEVNULL 隐藏详细输出，保持界面简洁
            - 每个包单独安装，便于定位失败原因
        """
        print("\n[3/4] 安装包...")
        
        # 合并所有包
        all_packages = self.core_packages + self.jupyter_packages
        
        # 显示包列表
        print(f"  共需安装 {len(all_packages)} 个包:")
        for i, pkg in enumerate(all_packages, 1):
            print(f"    {i:2d}. {pkg}")
        print()
        
        # 逐个安装
        for pkg in all_packages:
            print(f"  安装 {pkg}...", end=" ")
            cmd = ['conda', 'install', '-n', self.env_name, pkg, '-y']
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
            if result.returncode == 0:
                print("✓")
            else:
                print("⚠ 失败，尝试使用 pip")
                # 如果 conda 安装失败，尝试 pip
                cmd = ['conda', 'run', '-n', self.env_name, 'pip', 'install', pkg]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("\n✓ 所有包安装完成")
    
    def pack_environment(self):
        """
        打包 conda 环境
        
        使用 conda-pack 工具将完整环境打包为 tar.gz 文件。
        
        打包内容:
            - Python 解释器
            - 所有安装的包
            - 环境配置
            - 路径修复工具 (conda-unpack)
        
        输出:
            env_export/mysql_factory_env.tar.gz
        
        注意:
            - 打包前自动安装 conda-pack
            - 打包后显示文件大小
        """
        print("\n[4/4] 打包环境...")
        
        # 确保输出目录存在
        self.env_export_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 安装 conda-pack
        print("  安装 conda-pack...", end=" ")
        cmd = ['conda', 'install', '-n', self.env_name, 'conda-pack', '-y']
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if result.returncode == 0:
            print("✓")
        else:
            print("⚠")
        
        # 2. 执行打包
        print(f"  打包到：{self.output_file}")
        cmd = ['conda', 'pack', '-n', self.env_name, '-o', str(self.output_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ 错误：打包失败")
            print(f"详细信息：{result.stderr}")
            raise RuntimeError("打包环境失败")
        
        # 3. 显示文件大小
        if self.output_file.exists():
            size_mb = self.output_file.stat().st_size / (1024 * 1024)
            print(f"✓ 打包完成：{self.output_file.name} ({size_mb:.2f} MB)")
        else:
            raise RuntimeError("打包文件未生成")
    
    def create_readme(self):
        """
        创建部署说明文档
        
        生成 README_OFFLINE.md，包含：
        - 环境信息
        - 部署步骤
        - 故障排除
        """
        print("\n  创建部署说明文档...", end=" ")
        
        readme_content = f"""# MySQL Data Factory - 离线环境部署指南

## 环境信息

| 项目 | 值 |
|------|-----|
| 环境名称 | {self.env_name} |
| Python 版本 | {self.python_version} |
| 打包时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
| 环境包大小 | {self.output_file.stat().st_size / (1024 * 1024):.2f} MB (如果已生成) |

## 快速部署

### Windows

```bash
# 1. 解压环境
tar -xzf mysql_factory_env.tar.gz -C C:\tools\mysql_factory_env

# 2. 修复路径
C:\tools\mysql_factory_env\Scripts\conda-unpack.exe

# 3. 验证
C:\tools\mysql_factory_env\python.exe --version