#!/usr/bin/env python3
"""
验证数据库连通性。

这个脚本的定位非常明确：
它不是用来导数据、生成数据、插入数据的，
而是作为整个工具链最前面的“连通性自检入口”。

它只做最小、最安全的两步检查：
1. 连接数据库并执行 `SELECT 1`
2. 可选检查目标表是否存在

它不会写入任何业务数据，因此非常适合以下场景：
- 堡垒机首次部署后的自检
- 修改 `.env` 或 `.env.smoke` 后的快速确认
- 正式导模板或插入前的前置检查
- 安全评审时演示“我们首先只做只读连通检查”
"""

# 这行的作用：
# 让类型注解在运行时延迟解析。
# 对业务逻辑本身没有影响，主要是为了让类型注解写起来更自然。
from __future__ import annotations

# argparse：用于解析命令行参数，例如 --env-file、--table
import argparse

# os：用于读取环境变量，例如 TARGET_TABLE
import os

# sys：主要用于两件事
# 1. 调整 sys.path，确保项目内模块能被正确导入
# 2. 在脚本末尾通过 sys.exit(main()) 返回退出码
import sys

# Path：用于更清晰地处理文件路径
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# 当前文件一般位于：
#   <项目根目录>/scripts/test_connection.py
# 所以 parents[1] 就是项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 为了保证脚本在任何位置被调用时都能正确导入 src 下的模块，
# 这里把项目根目录加入 sys.path。
# 例如后面要导入：
#   from src.db.connection import DatabaseManager
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_env_file(env_file: str) -> Path:
    """
    把 env 文件路径统一解析成绝对路径。

    设计目的：
    - 用户可以传绝对路径
    - 也可以传相对路径，例如 .env / .env.smoke
    - 相对路径默认解释为“相对于项目根目录”

    这样做的好处是：
    用户不需要每次都手动写长路径。
    """

    # 先把字符串变成 Path 对象
    env_path = Path(env_file)

    # 如果不是绝对路径，就默认拼到项目根目录下
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    """
    加载指定 env 文件。

    这里采用“尽量加载，但不强依赖”的策略：
    - 如果安装了 python-dotenv，就加载
    - 如果没装，就直接跳过，不在这里报错

    这样做的原因：
    - 某些极简运行环境里可能没有 python-dotenv
    - 这时脚本仍然可以依赖系统环境变量运行

    这里显式使用 `utf-8-sig`，是为了兼容 Windows 环境下常见的 BOM `.env` 文件。
    """

    try:
        # 延迟导入，只有真的需要加载 env 文件时才尝试导入
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        # 如果没有安装 python-dotenv，就直接返回
        # 不在这里报错，是为了兼容“纯环境变量模式”
        return

    # resolve_env_file(env_file)：先把路径解析清楚
    # override=True：env 文件中的值覆盖已有环境变量
    # encoding="utf-8-sig"：兼容 Windows 下带 BOM 的文件
    load_dotenv(resolve_env_file(env_file), override=True, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    这里采用两段式解析：

    第一步：
    - 先只解析 `--env-file`
    - 先把对应 env 文件加载进来

    第二步：
    - 再正式解析全部参数
    - 这样正式参数的默认值就可以直接来自 env 文件

    例如：
    - `--table` 默认值可以直接读取 TARGET_TABLE
    """

    # -------------------------------------------------------------
    # 第一次：只解析 --env-file
    # -------------------------------------------------------------
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")

    # parse_known_args()：
    # - 只解析当前 parser 已知的参数
    # - 其余参数先留到后面正式 parser 再处理
    env_args, _ = env_parser.parse_known_args()

    # 先加载 env 文件
    maybe_load_dotenv(env_args.env_file)

    # -------------------------------------------------------------
    # 第二次：正式解析全部参数
    # -------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Test database connectivity from .env.")

    # 配置文件路径参数
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )

    # 可选表名参数
    # 默认值来自环境变量 TARGET_TABLE
    # 如果用户显式传入 --table，则优先使用命令行值
    parser.add_argument(
        "--table",
        default=os.getenv("TARGET_TABLE"),
        help="Optional table name to verify after SELECT 1.",
    )

    return parser.parse_args()


def table_exists(db, table_name: str) -> bool:
    """
    检查指定表是否存在。

    这里采用最简单、最容易解释的 SQL：
        SHOW TABLES LIKE %s

    参数说明：
    - db：数据库管理对象
    - table_name：要检查的表名

    返回：
    - True：表存在
    - False：表不存在

    为什么这里单独封装成函数：
    - 让 main() 主流程更清楚
    - 也更方便在评审时单独解释“表存在检查”这一步
    """

    # db.query() 返回结果列表
    # 只要有结果，就说明表存在
    rows = db.query("SHOW TABLES LIKE %s", (table_name,))
    return bool(rows)


def main() -> int:
    """
    脚本主入口。

    主流程非常短，非常适合作为“前置自检脚本”在会议上解释：

    1. 解析参数
    2. 创建数据库管理对象
    3. 打印当前连接目标（主机、端口、数据库）
    4. 建立连接
    5. 执行 SELECT 1
    6. 如果指定了表名，则额外检查该表是否存在
    7. 输出通过结果
    8. 无论成功失败都断开连接

    这个脚本最重要的特点是：
    - 只做只读检查
    - 不做任何写操作
    - 逻辑极简
    - 非常适合堡垒机首次验证和安全评审说明
    """

    # 解析命令行参数
    args = parse_args()

    # 延迟导入当前 3.0 配置/连接层
    # 这样用户只看 --help 时，不会过早触发数据库模块依赖
    from src.config.app_config import ConnectionConfig, load_dotenv_file
    from src.db.connection import DatabaseManager

    # 先按 3.0 方式加载 env，再构造连接配置
    load_dotenv_file(args.env_file)
    conn = ConnectionConfig.from_env()

    # 创建数据库管理对象
    db = DatabaseManager(config=conn)
    # 先把当前目标打印出来，方便操作者确认自己连的是哪个库
    # 这一步非常有用，尤其是在堡垒机上容易连错环境时
    print(f"Host: {db.host}")
    print(f"Port: {db.port}")
    print(f"Database: {db.database}")

    # 尝试建立数据库连接
    if not db.connect():
        print("[FAIL] Database connection failed.")
        return 1

    try:
        # ---------------------------------------------------------
        # 第一步：执行最小只读 SQL 检查
        # ---------------------------------------------------------
        # 这里只做最小读操作，不做任何写操作。
        # SELECT 1 是最常见、最安全的数据库连通检查语句。
        db.query("SELECT 1")
        print("[OK] SELECT 1 succeeded.")

        # ---------------------------------------------------------
        # 第二步：如果用户指定了表名，则额外检查该表是否存在
        # ---------------------------------------------------------
        if args.table:
            if table_exists(db, args.table):
                print(f"[OK] Target table exists: {args.table}")
            else:
                print(f"[FAIL] Target table not found: {args.table}")
                return 1

        # 到这里说明：
        # - 数据库能连通
        # - SELECT 1 能执行
        # - 若指定了表，则表存在检查也通过
        print("[DONE] Connectivity check passed.")
        return 0

    except Exception as exc:
        # 统一异常出口：
        # 如果在执行 SELECT 1 或表检查时发生任何异常，
        # 都走这里，打印失败信息并返回非 0 退出码
        print(f"[FAIL] Connectivity check failed: {exc}")
        return 1

    finally:
        # 无论成功还是失败，都要主动断开数据库连接
        # 这样更适合短连接风格，也更方便在评审时解释：
        # “这个脚本不会长期占用连接”
        db.disconnect()


# 标准 Python 脚本入口
# 只有当这个文件被直接运行时，才会执行 main()
if __name__ == "__main__":
    sys.exit(main())

