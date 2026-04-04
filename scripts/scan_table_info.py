#!/usr/bin/env python3
"""
扫描数据库表信息并保存到表配置文件。

这个脚本是 V1.1 的起点脚本，主要解决两个真实痛点：

1. 不想每次都手工填写表名、主键、唯一键、JSON 列
2. 希望后续生成和插入流程能直接复用扫描结果

输入：

- 数据库连接配置
- 可选的目标库名
- 可选的目标表列表

输出：

- config/table_profiles.json

适用场景：

- 第一次接入某个数据库
- 第一次接入某张表
- 想提前把表结构信息保存下来，减少后续人工配置
"""

# 这行的作用：
# 让类型注解延迟求值。
# 对业务逻辑没有影响，主要是为了让 list[str] 这类写法更自然。
from __future__ import annotations

# argparse：解析命令行参数，例如 --database、--table、--tables、--profile-file
import argparse

# os：读取环境变量，例如 DB_NAME、TABLE_PROFILE_PATH、DEFAULT_CHUNK_SIZE、INSERT_BATCH_SIZE
import os

# sys：用于两件事
# 1. 把项目根目录加入 sys.path，确保后面能导入 src 模块
# 2. 在文件末尾通过 sys.exit(main()) 返回退出码
import sys

# Path：比纯字符串路径更清晰，适合做路径拼接、绝对路径解析等操作
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# 当前文件路径一般形如：
#   <项目根目录>/scripts/scan_table_info.py
# parents[1] 对应项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 把项目根目录加入 sys.path，确保后面可以成功导入：
# - src.database
# - src.profile_store
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_env_file(env_file: str) -> Path:
    """
    解析 env 文件路径。

    规则：
    - 如果传入的是绝对路径，就直接使用
    - 如果传入的是相对路径，就默认相对于项目根目录

    这样做的好处是：
    - 用户可以写 .env 或 .env.smoke
    - 也可以写完整绝对路径
    - 最终都能被统一解析为明确的 Path 对象
    """

    # 先把字符串转成 Path 对象
    env_path = Path(env_file)

    # 如果不是绝对路径，就默认拼到项目根目录下
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    """
    加载指定 env 文件。

    这里采用“尽量加载，但不强依赖”的策略：
    - 如果环境里装了 python-dotenv，就加载
    - 如果没装，就直接跳过

    这样做的原因：
    - 某些极简环境可能没有 python-dotenv
    - 但脚本仍然可以依赖系统环境变量运行
    """

    try:
        # 延迟导入，只有真的需要时才加载
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        # 如果没装 python-dotenv，就直接返回，不在这里报错
        return

    # override=True：
    # env 文件中的值会覆盖已有环境变量
    # encoding="utf-8-sig"：
    # 兼容 Windows 下可能带 BOM 的文件
    load_dotenv(resolve_env_file(env_file), override=True, encoding="utf-8-sig")


def parse_table_list(raw_value: str | None) -> list[str]:
    """
    把逗号分隔的表名字符串转换成列表。

    例如：
    "table_a,table_b,table_c"
    -> ["table_a", "table_b", "table_c"]

    空值时返回空列表。
    """

    # 如果原始值为空、None、空字符串，则直接返回空列表
    if not raw_value:
        return []

    # split(",") 后逐个 strip() 去掉两端空格
    # 同时过滤掉空项
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    和其他脚本保持一致：
    1. 先预解析 --env-file
    2. 加载对应 env 文件
    3. 再正式解析全部参数

    这样做的好处是：
    - 后面的默认值可以直接从 env 文件读取
    - 例如 DB_NAME、TABLE_PROFILE_PATH
    """

    # -------------------------------------------------------------
    # 第一次：只解析 --env-file
    # -------------------------------------------------------------
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()

    # 先加载 env 文件
    maybe_load_dotenv(env_args.env_file)

    # -------------------------------------------------------------
    # 第二次：正式解析全部参数
    # -------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Scan table info and save table profiles.")

    # 运行配置文件路径
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )

    # 目标数据库名
    # 默认来自环境变量 DB_NAME
    parser.add_argument(
        "--database",
        default=os.getenv("DB_NAME"),
        help="Database name to scan. Defaults to DB_NAME from env.",
    )

    # 单张表模式
    # 这是一个更简单的参数写法，相当于 --tables 的简化版
    parser.add_argument(
        "--table",
        default="",
        help="Optional single table name. This is a simpler alias for --tables.",
    )

    # 多表模式
    # 支持用逗号分隔的表列表
    parser.add_argument(
        "--tables",
        default="",
        help="Optional comma-separated table list. If omitted, scan all tables in the database.",
    )

    # 输出的表配置 JSON 文件路径
    parser.add_argument(
        "--profile-file",
        default=os.getenv("TABLE_PROFILE_PATH", "config/table_profiles.json"),
        help="Path to the JSON table profile file.",
    )

    return parser.parse_args()


def resolve_default_chunk_size() -> int:
    """
    解析默认 chunk size。

    V1.1 的硬规则是单个 chunk 不允许超过 10000 行。
    所以这里即使环境变量写得更大，也会被强制压到 10000。

    优先数据来源：
    - 环境变量 DEFAULT_CHUNK_SIZE
    - 如果环境变量不合法，则回退到 5000
    """

    # 先读环境变量，默认值 5000
    raw_value = os.getenv("DEFAULT_CHUNK_SIZE", "5000")

    try:
        value = int(raw_value)
    except ValueError:
        # 如果环境变量写错了，例如写成 abc，就回退到 5000
        value = 5000

    # 如果是 0 或负数，也回退到 5000
    if value <= 0:
        value = 5000

    # V1.1 的上限硬限制为 10000
    if value > 10000:
        value = 10000

    return value


def resolve_default_batch_size() -> int:
    """
    解析默认 batch size。

    来源：
    - 环境变量 INSERT_BATCH_SIZE
    - 如果环境变量不合法，则回退到 500

    这里不像 chunk size 那样额外限制上限，
    因为 batch size 更多是数据库写入节奏问题，
    后续可由实际场景调整。
    """

    # 先读环境变量，默认 500
    raw_value = os.getenv("INSERT_BATCH_SIZE", "500")

    try:
        value = int(raw_value)
    except ValueError:
        # 如果环境变量写错，就回退到 500
        value = 500

    # 如果是 0 或负数，也回退到 500
    if value <= 0:
        value = 500

    return value


def build_table_profile(db, table_name: str, default_chunk_size: int, default_batch_size: int) -> dict:
    """
    为单张表构建配置。

    这个函数的职责很单一：
    - 给定数据库连接对象和表名
    - 从数据库里扫描该表的关键信息
    - 组装成一个 profile 字典，供后续写入 JSON 配置文件

    设计说明：

    - 优先使用数据库里真实扫描到的主键
    - 如果数据库里没有主键，则默认第一列为主键
    - 这个 fallback 是故意保留的，目的是让工具面对历史表时仍然能工作

    返回的 profile 至少包含：
    - 表名
    - 主键列
    - 主键来源
    - 唯一键列
    - JSON 列
    - 列顺序
    - 默认 chunk size
    - 默认 batch size
    """

    # 读取数据库里该表的列顺序
    # 这个顺序后续会用于：
    # - 导出 CSV 列顺序
    # - 插入时列顺序对齐
    column_order = db.get_column_names(table_name)

    # 读取数据库里真实定义的主键列
    primary_key_columns = db.get_primary_key_columns(table_name)

    # 默认先认为主键来源是“数据库真实主键”
    primary_key_source = "database_primary_key"

    # 如果数据库没有定义主键，则退回到“第一列为主键”
    if not primary_key_columns:
        first_column_name = db.get_first_column_name(table_name)

        # 如果连第一列都拿不到，说明表本身有问题或访问失败
        if not first_column_name:
            raise RuntimeError(f"Table {table_name} has no columns.")

        # 退回到第一列兜底
        primary_key_columns = [first_column_name]
        primary_key_source = "first_column_fallback"

    # 扫描唯一键列
    unique_key_columns = db.get_unique_key_columns(table_name)

    # 扫描 JSON 列
    json_columns = db.get_json_columns(table_name)

    # 如果唯一键里包含主键列，这里去重是为了让后续“只改必要唯一键”更清楚。
    # 也就是说：
    # - 主键已经会被单独处理
    # - 就不要在 unique_key_columns 里再重复出现一次
    unique_key_columns = [item for item in unique_key_columns if item not in primary_key_columns]

    # 返回单张表的 profile 结构
    return {
        "table_name": table_name,
        "primary_key_columns": primary_key_columns,
        "primary_key_source": primary_key_source,
        "unique_key_columns": unique_key_columns,
        "json_columns": json_columns,
        "column_order": column_order,
        "default_chunk_size": default_chunk_size,
        "default_batch_size": default_batch_size,
    }


def main() -> int:
    """
    脚本主入口。

    主流程非常直接，适合在评审会上逐步讲解：

    1. 解析参数
    2. 检查数据库名
    3. 决定要扫描哪些表
    4. 解析默认 chunk size / batch size
    5. 建立数据库连接
    6. 如果没指定表，则扫描整个库的表列表
    7. 加载已有 profile 文件
    8. 逐表扫描并更新配置
    9. 保存到 table_profiles.json
    10. 无论成功失败都断开数据库连接
    """

    # 解析命令行参数
    args = parse_args()

    # 如果数据库名为空，就无法继续
    if not args.database:
        print("[ERROR] Database name is required. Please set DB_NAME or use --database.")
        return 1

    # 延迟导入项目内模块
    # 这样用户只看 --help 时，不会过早依赖数据库模块
    from src.database import DatabaseManager
    from src.profile_store import load_profile_store, save_profile_store

    # 这里最终要形成一个待扫描表列表
    table_names = []

    # 如果用户明确传了 --table，则优先使用单表模式
    if args.table:
        table_names = [args.table.strip()]
    else:
        # 否则解析 --tables
        table_names = parse_table_list(args.tables)

    # 解析默认 chunk size
    default_chunk_size = resolve_default_chunk_size()

    # 解析默认 batch size
    default_batch_size = resolve_default_batch_size()

    # 建立数据库连接对象
    # 这里显式传 database=args.database，是为了允许扫描指定库
    db = DatabaseManager(database=args.database)

    # 尝试连接数据库
    if not db.connect():
        print("[ERROR] Database connection failed.")
        return 1

    try:
        # 如果用户既没传 --table，也没传 --tables，
        # 就默认扫描整个数据库中的所有表
        if not table_names:
            table_names = db.show_tables()

        # 如果数据库里也没有表，直接报错
        if not table_names:
            print("[ERROR] No tables found in the target database.")
            return 1

        # 读取已有 profile 文件
        # 如果文件不存在，load_profile_store() 通常会返回一个空结构
        profile_path, profile_data = load_profile_store(args.profile_file)

        # 记录当前扫描的数据库名
        profile_data["database"] = args.database

        # 取出 tables 节点；如果没有，就创建一个空 dict
        tables_node = profile_data.setdefault("tables", {})

        # 先打印本次任务的总体信息，方便人工确认
        print(f"Profile file: {profile_path}")
        print(f"Database: {args.database}")
        print(f"Tables to scan: {', '.join(table_names)}")
        print(f"Default chunk size: {default_chunk_size}")
        print(f"Default batch size: {default_batch_size}")
        print()

        # 逐张表扫描
        for table_name in table_names:
            print(f"[SCAN] {table_name}")

            # 为当前表构建 profile
            table_profile = build_table_profile(
                db,
                table_name,
                default_chunk_size,
                default_batch_size,
            )

            # 保存到 tables 节点
            # 这里如果表已存在，会直接覆盖为最新扫描结果
            tables_node[table_name] = table_profile

            # 打印当前表扫描结果，方便人工检查
            print(f"  Primary key columns: {table_profile['primary_key_columns']}")
            print(f"  Primary key source: {table_profile['primary_key_source']}")
            print(f"  Unique key columns: {table_profile['unique_key_columns']}")
            print(f"  JSON columns: {table_profile['json_columns']}")
            print(f"  Column count: {len(table_profile['column_order'])}")
            print()

        # 保存 profile 文件
        saved_path = save_profile_store(profile_data, str(profile_path))

        print(f"[DONE] Table profiles saved to: {saved_path}")
        return 0

    except Exception as exc:
        # 统一错误出口，避免直接抛原始 traceback 给用户
        print(f"[ERROR] Failed to scan table info: {exc}")
        return 1

    finally:
        # 无论成功失败，都主动断开数据库连接
        # 这样更符合短连接、易解释的风格
        db.disconnect()


# 标准 Python 脚本入口
if __name__ == "__main__":
    sys.exit(main())