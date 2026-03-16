#!/usr/bin/env python3
"""
离线环境打包脚本 - 简化版
"""

import subprocess
import sys
from pathlib import Path

def main():
    env_name = "mysql_factory"
    project_root = Path(__file__).parent.parent
    env_export_dir = project_root / "env_export"
    output_file = env_export_dir / f"{env_name}_env.tar.gz"
    
    print("=" * 60)
    print("MySQL Data Factory - 离线环境构建")
    print("=" * 60)
    
    # 1. 检查 conda
    print("\n[1/4] 检查 conda...")
    result = subprocess.run(['conda', '--version'], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ 错误: conda 未安装或不可用")
        sys.exit(1)
    print("✓ Conda 可用")
    
    # 2. 创建环境
    print(f"\n[2/4] 创建 conda 环境: {env_name}")
    subprocess.run(['conda', 'create', '-n', env_name, 'python=3.10', '-y'])
    print("✓ 环境创建成功")
    
    # 3. 安装包
    print("\n[3/4] 安装包...")
    packages = [
        'pymysql', 'sqlalchemy', 'pandas', 'numpy', 'faker',
        'python-dotenv', 'loguru', 'tqdm', 'pyarrow',
        'jupyter', 'notebook', 'ipykernel', 'mysql-connector-python'
    ]
    
    for pkg in packages:
        print(f"  安装 {pkg}...")
        subprocess.run(['conda', 'install', '-n', env_name, pkg, '-y'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("✓ 所有包安装完成")
    
    # 4. 打包
    print("\n[4/4] 打包环境...")
    env_export_dir.mkdir(parents=True, exist_ok=True)
    
    # 安装 conda-pack
    print("  安装 conda-pack...")
    subprocess.run(['conda', 'install', '-n', env_name, 'conda-pack', '-y'],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 打包
    subprocess.run(['conda', 'pack', '-n', env_name, '-o', str(output_file)])
    
    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"✓ 打包完成: {output_file} ({size_mb:.2f} MB)")
    
    print("\n" + "=" * 60)
    print("🎉 离线环境构建完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()