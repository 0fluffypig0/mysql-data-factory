#!/usr/bin/env python3
"""
构建用于堡垒机离线部署的最小 Python 运行环境。

这个脚本的目标非常明确：
1. 在有网的机器上创建一个专用的 conda 环境。
2. 根据 requirements.txt 安装项目所需依赖。
3. 在该环境中安装 conda-pack。
4. 把整个环境打包成一个 .tar.gz 文件。
5. 后续把这个压缩包连同项目代码一起带到堡垒机，即可离线部署。

这个脚本不参与业务数据处理，它只负责“打包离线运行环境”。
适用场景：
- 第一次准备堡垒机离线运行包
- 升级依赖后重新打包
- 在发布新版本前重新生成最新离线环境
"""

# 这行的作用：
# 让类型注解在运行时延迟解析。
# 对实际业务逻辑没有影响，主要是为了让 list[str] 这类注解写起来更自然。
from __future__ import annotations

# argparse：解析命令行参数，例如 --env-name、--python-version、--rebuild
import argparse

# subprocess：用于执行外部命令，例如 conda create、pip install、conda-pack
import subprocess

# sys：主要用于两件事
# 1. 获取当前 Python 解释器路径，从而推断默认 conda.bat 路径
# 2. 在脚本结尾用 sys.exit(main()) 返回退出码
import sys

# Path：比字符串路径更清晰，适合做路径拼接、存在性检查、绝对路径解析等操作
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# 当前文件一般位于：
#   <项目根目录>/scripts/build_offline_env.py
# parents[1] 对应项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------
# 默认 conda 可执行文件路径
# ---------------------------------------------------------------------
# 这里的思路是：
# 先拿到当前正在运行这个脚本的 Python 解释器路径，例如：
#   D:\016.Miniconda\python.exe
# 然后假定同级结构下存在：
#   D:\016.Miniconda\condabin\conda.bat
#
# 这个默认值适合你当前这种“用 Miniconda 自己的 Python 去执行脚本”的场景。
DEFAULT_CONDA_EXE = Path(sys.executable).resolve().parent / "condabin" / "conda.bat"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """
    执行一条外部命令，并在控制台打印该命令。

    参数说明：
    - cmd：要执行的命令列表，例如 ["cmd.exe", "/d", "/c", "conda.bat", "--version"]
    - check：如果为 True，则当返回码不是 0 时抛出异常

    设计目的：
    - 所有外部命令都走这个统一入口，方便排查问题
    - 先把命令打印出来，便于人工确认脚本到底做了什么
    - 若失败则统一抛出 RuntimeError，而不是到处手写 returncode 判断
    """

    # 把命令打印出来，方便人工排查
    print(f"[RUN] {' '.join(cmd)}")

    # 执行命令
    # cwd=PROJECT_ROOT：确保命令在项目根目录下执行
    # text=True：让 stdout/stderr 按文本方式处理，而不是 bytes
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True)

    # 如果要求 check，并且命令执行失败，则抛异常
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")

    return result


def conda_command(conda_exe: Path, *args: str) -> list[str]:
    """
    生成一条可执行的 conda 命令列表。

    之所以单独封装，是因为：
    - Windows 下如果 conda 可执行文件是 .bat，就不能像普通 exe 那样直接调用
    - 这时需要通过：
        cmd.exe /d /c conda.bat ...
      的形式执行
    - 如果不是 .bat，则直接执行即可

    参数：
    - conda_exe：conda 的实际路径
    - *args：要传给 conda 的后续参数，例如 "create", "-p", "xxx"

    返回：
    - 一条可直接交给 subprocess.run() 的命令列表
    """

    # 如果 conda_exe 是 .bat 文件（Windows 常见情况）
    if conda_exe.suffix.lower() == ".bat":
        # 通过 cmd.exe 调用 .bat
        # /d：禁用 AutoRun，减少环境干扰
        # /c：执行完后退出
        return ["cmd.exe", "/d", "/c", str(conda_exe), *args]

    # 如果不是 .bat，例如是 conda.exe 或其他可执行文件，则直接调用
    return [str(conda_exe), *args]


def conda_env_exists(conda_exe: Path, env_prefix: Path) -> bool:
    """
    判断指定的 conda 环境是否已经存在且可用。

    检查方式非常直接：
    - 尝试执行：
        conda run -p <env_prefix> python --version
    - 如果返回码为 0，说明这个环境存在并可正常运行 Python
    - 否则视为不存在或不可用

    这样做的好处：
    - 不依赖 conda env list 的文本解析
    - 判断标准更贴近真实使用场景：这个环境到底能不能跑 Python
    """

    result = subprocess.run(
        conda_command(conda_exe, "run", "-p", str(env_prefix), "python", "--version"),
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,   # 不打印输出，避免刷屏
        stderr=subprocess.DEVNULL,   # 不打印错误，失败仅通过返回码判断
        text=True,
    )

    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    本脚本支持的参数主要围绕“如何创建并打包这个离线环境”：

    - env-name：环境名字
    - env-prefix：环境安装目录
    - python-version：Python 版本
    - output-dir：输出目录
    - requirements：requirements.txt 路径
    - conda-exe：conda 可执行文件路径
    - rebuild：是否强制重建环境
    """

    parser = argparse.ArgumentParser(
        description="Build a minimal conda-pack offline environment for mysql-data-factory.",
    )

    # 环境名称
    # 主要用于输出文件命名，例如 mysql_factory_env.tar.gz
    parser.add_argument("--env-name", default="mysql_factory")

    # 环境安装目录
    # 如果不传，就默认放到：
    #   <项目根目录>/.offline_envs/<env-name>
    parser.add_argument(
        "--env-prefix",
        default="",
        help="Optional explicit conda environment prefix. Defaults to .offline_envs/<env-name> under the repo.",
    )

    # Python 版本
    parser.add_argument("--python-version", default="3.10")

    # 输出目录
    # 默认输出到项目根目录下的 env_export/
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "env_export"))

    # requirements.txt 路径
    parser.add_argument("--requirements", default=str(PROJECT_ROOT / "requirements.txt"))

    # conda 可执行文件路径
    parser.add_argument("--conda-exe", default=str(DEFAULT_CONDA_EXE))

    # --rebuild：
    # 如果目标环境已存在，则先删除再重建
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Remove the target conda environment first if it already exists.",
    )

    return parser.parse_args()


def main() -> int:
    """
    脚本主入口。

    主流程非常直白，适合在评审或说明会上逐步讲解：

    1. 解析参数
    2. 解析 requirements / output / conda / env_prefix 路径
    3. 检查关键文件是否存在
    4. 先执行 conda --version，确认 conda 可用
    5. 如果要求 rebuild 且环境已存在，则删除环境
    6. 如果环境不存在，则创建新环境
    7. 在环境中安装 requirements.txt 依赖
    8. 在环境中安装 conda-pack
    9. 调用 conda-pack 把环境打包成 .tar.gz
    10. 检查输出包是否真的生成
    11. 打印结果摘要

    这个脚本不处理任何业务数据，只负责“准备堡垒机的离线 Python 运行环境”。
    """

    # 解析命令行参数
    args = parse_args()

    # requirements 文件路径
    requirements_file = Path(args.requirements).resolve()

    # 输出目录
    output_dir = Path(args.output_dir).resolve()

    # 最终输出的离线环境包名，例如：
    #   env_export/mysql_factory_env.tar.gz
    output_file = output_dir / f"{args.env_name}_env.tar.gz"

    # conda 可执行文件路径
    conda_exe = Path(args.conda_exe).resolve()

    # conda 环境实际安装目录：
    # - 如果用户显式给了 --env-prefix，就使用那个目录
    # - 否则默认使用项目内的 .offline_envs/<env-name>
    env_prefix = (
        Path(args.env_prefix).resolve()
        if args.env_prefix
        else (PROJECT_ROOT / ".offline_envs" / args.env_name)
    )

    # -------------------------------------------------------------
    # 第一步：前置检查
    # -------------------------------------------------------------
    # requirements 文件不存在，直接失败
    if not requirements_file.exists():
        print(f"[ERROR] requirements file not found: {requirements_file}")
        return 1

    # conda 可执行文件不存在，也直接失败
    if not conda_exe.exists():
        print(f"[ERROR] conda executable not found: {conda_exe}")
        return 1

    try:
        # ---------------------------------------------------------
        # 第二步：先确认 conda 本身可用
        # ---------------------------------------------------------
        # 这一步的目的不是创建环境，只是先确认 conda 能执行
        run(conda_command(conda_exe, "--version"))

        # ---------------------------------------------------------
        # 第三步：如果指定了 --rebuild，且环境已存在，则先删除
        # ---------------------------------------------------------
        if args.rebuild and conda_env_exists(conda_exe, env_prefix):
            run(conda_command(conda_exe, "remove", "-p", str(env_prefix), "--all", "-y"))

        # ---------------------------------------------------------
        # 第四步：如果环境不存在，则创建新环境
        # ---------------------------------------------------------
        if not conda_env_exists(conda_exe, env_prefix):
            # 确保父目录存在
            env_prefix.parent.mkdir(parents=True, exist_ok=True)

            # 创建 conda 环境
            # 这里默认安装：
            # - 指定版本 Python
            # - pip
            run(
                conda_command(
                    conda_exe,
                    "create",
                    "-p",
                    str(env_prefix),
                    f"python={args.python_version}",
                    "pip",
                    "-y",
                )
            )
        else:
            # 如果环境已存在且没要求 rebuild，就直接复用
            print(f"[INFO] Reusing existing conda environment: {env_prefix}")

        # ---------------------------------------------------------
        # 第五步：安装 requirements.txt 中的依赖
        # ---------------------------------------------------------
        # 这里使用：
        #   conda run -p <env_prefix> python -m pip install -r requirements.txt
        # 目的是确保依赖安装到指定环境，而不是当前系统 Python
        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements_file),
            )
        )

        # ---------------------------------------------------------
        # 第六步：在目标环境中安装 conda-pack
        # ---------------------------------------------------------
        # 因为后面打包环境要靠 conda-pack，所以这里显式装进去
        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "pip",
                "install",
                "conda-pack",
            )
        )

        # ---------------------------------------------------------
        # 第七步：准备输出目录
        # ---------------------------------------------------------
        output_dir.mkdir(parents=True, exist_ok=True)

        # 如果输出文件已存在，先删掉旧文件，避免和旧包混淆
        if output_file.exists():
            output_file.unlink()

        # ---------------------------------------------------------
        # 第八步：正式打包环境
        # ---------------------------------------------------------
        # 使用 conda-pack 的 CLI 入口：
        #   python -m conda_pack.cli
        #
        # 参数说明：
        # -p <env_prefix>：指定要打包的环境路径
        # -o <output_file>：指定输出 tar.gz 文件
        # --force：允许覆盖已有输出文件
        run(
            conda_command(
                conda_exe,
                "run",
                "-p",
                str(env_prefix),
                "python",
                "-m",
                "conda_pack.cli",
                "-p",
                str(env_prefix),
                "-o",
                str(output_file),
                "--force",
            )
        )

        # ---------------------------------------------------------
        # 第九步：检查打包结果是否真实存在
        # ---------------------------------------------------------
        if not output_file.exists():
            print(f"[ERROR] output file was not created: {output_file}")
            return 1

        # 计算输出文件大小（MB）
        size_mb = output_file.stat().st_size / (1024 * 1024)

        # ---------------------------------------------------------
        # 第十步：输出结果摘要
        # ---------------------------------------------------------
        print()
        print("Build complete.")
        print(f"Environment prefix: {env_prefix}")
        print(f"Output: {output_file}")
        print(f"Size: {size_mb:.2f} MB")
        print("Next step: copy the repository plus env_export/ to the bastion host and run bin\\setup_offline.bat.")
        return 0

    except RuntimeError as exc:
        # 统一处理 run() 抛出的命令执行异常
        print(f"[ERROR] {exc}")
        return 1


# 标准 Python 脚本入口
# 只有当这个文件被直接运行时，才会执行 main()
if __name__ == "__main__":
    sys.exit(main())