#!/usr/bin/env python3
"""
对 chunk CSV 做 dry-run 检查，并按 batch 插入单表数据。

这个脚本是 V1.1 的核心插入步骤，设计目标如下：
1. 支持输入单个 CSV，也支持输入 chunk 目录。
2. dry-run 先把明显问题挡在前面，避免直接写库。
3. 正式插入时，每个 batch 单独建连、提交、断连。
4. 如果遇到连接失效，只重试 1 次；第二次仍失败就立刻停止。

为什么这样设计：
- 真实堡垒机环境里，账号和连接往往不稳定。
- 长连接更容易在中途过期，导致整批任务失败。
- 按 batch 短连接虽然看起来“笨”，但最稳，也最好解释。
"""

# 这一行的作用：
# 让类型注解在运行时延迟解析。
# 对业务逻辑本身没有影响，主要是为了让 list[str] 这类注解写起来更自然。
from __future__ import annotations

# argparse：解析命令行参数，例如 --table、--input、--dry-run、--batch-size
import argparse

# json：对 JSON 列做合法性校验和规范化
import json

# os：读取环境变量，例如 TARGET_TABLE、INSERT_BATCH_SIZE、JSON_COLUMNS
import os

# re：表名正则校验
import re

# sys：用于两件事
# 1. 把项目根目录加入 sys.path，保证能导入 src 下模块
# 2. 在文件最后通过 sys.exit(main()) 返回退出码
import sys

# Path：用于路径拼接和文件/目录判断，写法比纯字符串更清晰
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# 当前文件路径一般形如：
#   <项目根目录>/scripts/insert_csv.py
# parents[1] 对应项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 把项目根目录加入 sys.path，确保后面可以正确导入：
# - src.chunk_csv
# - src.database
# - src.profile_store
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------
# 安全校验：表名正则
# ---------------------------------------------------------------------
# 限制表名只能由：
# - 字母
# - 数字
# - 下划线
# 组成。
#
# 这样做的目的：
# 因为后面 SQL 会把表名拼到字符串里，所以要防止非法表名进入 SQL。
TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def resolve_env_file(env_file: str) -> Path:
    """
    把用户传入的 env 文件路径解析成绝对路径。

    规则：
    - 如果本身就是绝对路径，直接使用
    - 如果是相对路径，则默认相对于项目根目录
    """

    # 先把字符串转成 Path 对象
    env_path = Path(env_file)

    # 如果不是绝对路径，就默认拼到项目根目录下面
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    """
    尝试加载 .env 文件。

    这里采用“尽量加载，但不强依赖”的策略：
    - 如果安装了 python-dotenv，就加载
    - 如果没装，就直接跳过

    这样做的原因：
    - 有些极简环境可能没有 python-dotenv
    - 这种情况下仍可以依赖系统环境变量运行
    """

    try:
        # 延迟导入
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        # 如果没装 python-dotenv，就直接返回，不在这里报错
        return

    # override=True：
    # env 文件中的值覆盖已有环境变量
    # encoding="utf-8-sig"：
    # 兼容 Windows 下可能带 BOM 的 .env 文件
    load_dotenv(resolve_env_file(env_file), override=True, encoding="utf-8-sig")


def parse_column_list(raw_value: str | None) -> list[str]:
    """
    把逗号分隔的列名字符串解析成列表。

    例如：
    "id,code,created_at"
    -> ["id", "code", "created_at"]

    如果为空，则返回空列表。
    """

    if not raw_value:
        return []

    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    这里分两步做：
    1. 先预解析 --env-file
    2. 加载对应 env 文件
    3. 再正式解析全部参数

    这样做的好处是：
    后面参数默认值可以来自 env 文件，而不是只能依赖系统环境变量。
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
    parser = argparse.ArgumentParser(
        description="Dry-run or insert one chunk CSV file or one chunk directory."
    )

    # 配置文件路径
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )

    # 目标表名，默认来自 TARGET_TABLE
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))

    # 表配置文件路径
    parser.add_argument(
        "--profile-file",
        default=os.getenv("TABLE_PROFILE_PATH", "config/table_profiles.json"),
        help="Path to the table profile JSON file.",
    )

    # 输入路径：
    # 可以是一个 CSV 文件，也可以是一个 chunk 目录
    parser.add_argument("--input", help="Path to one CSV file or a chunk directory.")

    # 插入批次大小
    parser.add_argument(
        "--batch-size",
        type=int,
        help="How many rows one INSERT batch should contain.",
    )

    # 主键列，可手工指定
    parser.add_argument("--pk-cols")

    # JSON 列，可手工指定
    parser.add_argument("--json-cols")

    # dry-run：只做检查，不真正写库
    parser.add_argument("--dry-run", action="store_true")

    # skip-db-check：
    # 允许在 dry-run 模式下，不连 MySQL，仅对 CSV 本身做结构和内容检查
    parser.add_argument(
        "--skip-db-check",
        action="store_true",
        help="Allow dry-run validation without connecting to MySQL or checking table schema.",
    )

    return parser.parse_args()


def validate_table_name(table_name: str) -> str:
    """
    校验表名是否合法。

    表名必须：
    - 非空
    - 满足字母/数字/下划线规则

    目的是避免把非法表名带进 SQL 中。
    """

    if not table_name or not TABLE_NAME_RE.match(table_name):
        raise ValueError("TARGET_TABLE or --table must be a single table name.")

    return table_name


def get_profile_list(profile: dict | None, key_name: str) -> list[str]:
    """
    从表配置 profile 中读取列表型字段。

    例如：
    - primary_key_columns
    - unique_key_columns
    - json_columns

    如果 profile 不存在，或字段类型不对，返回空列表。
    """

    if not profile:
        return []

    value = profile.get(key_name, [])

    if not isinstance(value, list):
        return []

    return [str(item).strip() for item in value if str(item).strip()]


def get_profile_int(profile: dict | None, key_name: str) -> int | None:
    """
    从表配置 profile 中读取整数型字段。

    例如：
    - default_batch_size

    如果没有、为空、类型不对或不能转 int，就返回 None。
    """

    if not profile:
        return None

    value = profile.get(key_name)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_batch_size(args: argparse.Namespace, profile: dict | None) -> int:
    """
    确定最终使用的 batch size。

    优先级：
    1. 命令行 --batch-size
    2. profile 中的 default_batch_size
    3. 环境变量 INSERT_BATCH_SIZE
    4. 默认值 500

    最后还会检查 batch size 必须大于 0。
    """

    # 1. 优先使用命令行参数
    raw_value = args.batch_size

    # 2. 如果命令行没传，就看表配置
    if raw_value is None:
        raw_value = get_profile_int(profile, "default_batch_size")

    # 3. 如果表配置也没给，就看环境变量
    if raw_value is None:
        raw_value = int(os.getenv("INSERT_BATCH_SIZE", "500"))

    # 合法性检查
    if int(raw_value) <= 0:
        raise ValueError("--batch-size must be greater than 0.")

    return int(raw_value)


def resolve_primary_key_columns(
    args: argparse.Namespace,
    profile: dict | None,
    db,
    table_name: str,
    table_columns: list[str] | None,
) -> tuple[list[str], str]:
    """
    按优先级确定主键列列表。

    返回：
    - 主键列列表
    - 主键来源说明

    优先级：
    1. 命令行 --pk-cols
    2. 表配置文件
    3. 环境变量 PRIMARY_KEY_COLUMNS
    4. 数据库扫描
    5. 第一列兜底
    """

    # 1. 命令行
    configured_columns = parse_column_list(args.pk_cols)
    if configured_columns:
        return configured_columns, "command_or_env"

    # 2. 表配置文件
    profile_columns = get_profile_list(profile, "primary_key_columns")
    if profile_columns:
        return profile_columns, "table_profile"

    # 3. 环境变量
    env_columns = parse_column_list(os.getenv("PRIMARY_KEY_COLUMNS"))
    if env_columns:
        return env_columns, "env"

    # 4. 数据库扫描
    if db is not None:
        database_columns = db.get_primary_key_columns(table_name)
        if database_columns:
            return database_columns, "database_scan"

    # 5. 最后兜底：第一列
    if table_columns:
        return [table_columns[0]], "first_column_fallback"

    raise ValueError("Could not determine primary key columns for insert_csv.py.")


def resolve_json_columns(args: argparse.Namespace, profile: dict | None, db, table_name: str) -> list[str]:
    """
    解析 JSON 列列表。

    优先级：
    1. 命令行 --json-cols
    2. 表配置文件
    3. 环境变量 JSON_COLUMNS
    4. 数据库扫描

    这里的目标很简单：
    只确定“哪些列是 JSON”，不在这里修改业务内容。
    """

    configured_columns = parse_column_list(args.json_cols)
    if configured_columns:
        return configured_columns

    profile_columns = get_profile_list(profile, "json_columns")
    if profile_columns:
        return profile_columns

    env_columns = parse_column_list(os.getenv("JSON_COLUMNS"))
    if env_columns:
        return env_columns

    if db is not None:
        return db.get_json_columns(table_name)

    return []


def normalize_json_value(raw_value: object) -> tuple[bool, str | None, str | None]:
    """
    校验并规范化一个 JSON 单元格。

    返回值含义：
    - 第一个值：是否为合法 JSON
    - 第二个值：规范化后的 JSON 字符串；如果空则返回 None
    - 第三个值：错误信息；合法时为 None

    规则：
    - 空值 -> 视为合法，并记为 None
    - 非空 -> 必须能 json.loads 成功
    - 成功后统一压缩成规范 JSON 字符串
    """

    # None 统一当成空字符串处理
    raw_text = "" if raw_value is None else str(raw_value).strip()

    # 空字符串视为“合法空值”
    if raw_text == "":
        return True, None, None

    try:
        # 先尝试解析
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        # 非法 JSON：返回 False 和具体错误信息
        return False, raw_text, f"{exc.msg} (char {exc.pos})"

    # 合法 JSON：重新规范化输出
    normalized = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return True, normalized, None


def build_pk_key(row: dict[str, str], pk_columns: list[str]) -> tuple[str, ...]:
    """
    从一行数据中抽取主键值，组成一个元组。

    这样做的原因：
    - 方便统一处理单主键和联合主键
    - 后面可以把这个元组放进 set 中检查重复
    """

    return tuple((row.get(column) or "").strip() for column in pk_columns)


def is_empty_pk_key(pk_key: tuple[str, ...]) -> bool:
    """
    判断主键组合里是否有空值。

    只要联合主键中的任意一列为空，就视为无效主键。
    """

    return any(value == "" for value in pk_key)


def create_validation_summary() -> dict:
    """
    创建 dry-run 检查结果统计对象。

    之所以单独封装，是为了让后面 validate_csv_files 的逻辑更直白。
    """

    return {
        "file_count": 0,                # 一共检查了多少个 CSV 文件
        "total_rows": 0,               # 总行数
        "empty_pk_rows": 0,            # 主键为空的行数
        "duplicate_pk_rows": 0,        # 输入中主键重复的行数
        "invalid_json_rows": 0,        # 非法 JSON 行数
        "invalid_json_examples": [],   # 最多保留 5 个 JSON 错误示例
        "all_columns": [],             # CSV 表头
    }


def get_first_csv_column(csv_files: list[Path]) -> list[str]:
    """
    读取第一个 CSV 文件的表头。

    主要用于 skip-db-check 场景下，
    当无法连接数据库时，至少可以从 CSV 中拿到列顺序，
    并据此做“第一列兜底主键”的逻辑。
    """

    from src.chunk_csv import read_csv_rows

    if not csv_files:
        return []

    fieldnames, _ = read_csv_rows(csv_files[0])
    return fieldnames


def add_invalid_json_example(summary: dict, file_path: Path, row_number: int, column: str, value: str, error: str) -> None:
    """
    向 dry-run 结果中追加一个 JSON 错误示例。

    这里最多只保留 5 个示例，避免错误太多时刷屏。
    """

    if len(summary["invalid_json_examples"]) >= 5:
        return

    summary["invalid_json_examples"].append(
        {
            "file": str(file_path),
            "row": row_number,
            "column": column,
            "value": value,
            "error": error,
        }
    )


def validate_csv_files(
    csv_files: list[Path],
    pk_columns: list[str],
    json_columns: list[str],
    table_columns: list[str] | None,
) -> dict:
    """
    对输入的 chunk 文件做 dry-run 级别校验。

    这一步只统计和检查，不做数据库写入。
    之所以把 dry-run 和正式插入拆开，是为了让风险点在写库前先暴露出来。

    检查内容包括：
    - 各文件表头是否一致
    - 主键列是否存在
    - JSON 列是否存在
    - CSV 是否包含数据库不存在的列
    - 主键是否为空
    - 输入内部是否有重复主键
    - JSON 是否合法
    """

    from src.chunk_csv import read_csv_rows

    # 初始化统计摘要
    summary = create_validation_summary()

    # seen_pk_keys 用来检查输入内部主键重复
    seen_pk_keys: set[tuple[str, ...]] = set()

    # 逐文件检查
    for file_path in csv_files:
        fieldnames, rows = read_csv_rows(file_path)
        summary["file_count"] += 1

        # 第一个文件的表头作为“标准表头”
        if not summary["all_columns"]:
            summary["all_columns"] = fieldnames

        # 后续文件如果表头不一致，直接报错
        elif summary["all_columns"] != fieldnames:
            raise ValueError(f"CSV header mismatch detected: {file_path}")

        # 检查主键列是否都存在
        missing_pk_columns = [column for column in pk_columns if column not in fieldnames]
        if missing_pk_columns:
            raise ValueError(f"Primary key columns not found in CSV: {missing_pk_columns}")

        # 检查 JSON 列是否都存在
        missing_json_columns = [column for column in json_columns if column not in fieldnames]
        if missing_json_columns:
            raise ValueError(f"JSON columns not found in CSV: {missing_json_columns}")

        # 如果已经连库获取了真实表字段，则顺便检查 CSV 有没有多余列
        if table_columns is not None:
            unknown_columns = [column for column in fieldnames if column not in table_columns]
            if unknown_columns:
                raise ValueError(f"CSV contains columns that do not exist in the table: {unknown_columns}")

        # 逐行检查
        # start=2 是因为第 1 行是 CSV 表头，所以数据从第 2 行开始计数
        for row_index, row in enumerate(rows, start=2):
            summary["total_rows"] += 1

            # 构造当前行的主键组合
            pk_key = build_pk_key(row, pk_columns)

            # 检查主键是否为空
            if is_empty_pk_key(pk_key):
                summary["empty_pk_rows"] += 1
            else:
                # 检查输入内部是否重复
                if pk_key in seen_pk_keys:
                    summary["duplicate_pk_rows"] += 1
                else:
                    seen_pk_keys.add(pk_key)

            # 逐列检查 JSON
            for column in fieldnames:
                raw_value = row.get(column, "")

                if column in json_columns:
                    is_valid, normalized_value, error_message = normalize_json_value(raw_value)

                    if not is_valid:
                        summary["invalid_json_rows"] += 1
                        add_invalid_json_example(
                            summary,
                            file_path,
                            row_index,
                            column,
                            "" if raw_value is None else str(raw_value),
                            error_message or "invalid JSON",
                        )
                        continue

                    # 合法 JSON 不需要在 dry-run 阶段再做别的事
                    continue

    return summary


def normalize_rows_for_insert(file_path: Path, json_columns: list[str]) -> tuple[list[str], list[dict[str, str | None]]]:
    """
    为正式插入重新读取并规范化一个 chunk 文件。

    这里选择“正式插入前再按文件读取一次”，而不是把所有 chunk 预先长期留在内存中。
    原因很简单：
    - 每个 chunk 已被限制在 10000 行以内
    - 单个 chunk 读入内存是可控的
    - 这样比把所有 chunk 常驻内存更稳
    """

    from src.chunk_csv import read_csv_rows

    # 读取一个 chunk 文件
    fieldnames, rows = read_csv_rows(file_path)

    # 存放规范化后的结果
    normalized_rows: list[dict[str, str | None]] = []

    for row in rows:
        normalized_row: dict[str, str | None] = {}

        for column in fieldnames:
            raw_value = row.get(column, "")

            # JSON 列需要做合法性校验和规范化
            if column in json_columns:
                is_valid, normalized_value, error_message = normalize_json_value(raw_value)

                # 理论上 dry-run 已经检查过一次，这里如果还报错，
                # 说明输入文件在两次操作之间被改过，或者前面漏检了
                if not is_valid:
                    raise ValueError(
                        f"Invalid JSON detected during insert preparation: file={file_path}, "
                        f"column={column}, error={error_message}"
                    )

                normalized_row[column] = normalized_value
            else:
                # 非 JSON 列统一保留为字符串
                normalized_row[column] = "" if raw_value is None else str(raw_value)

        normalized_rows.append(normalized_row)

    return fieldnames, normalized_rows


def print_dry_run_summary(
    table_name: str,
    input_path: Path,
    batch_size: int,
    pk_columns: list[str],
    json_columns: list[str],
    summary: dict,
) -> None:
    """
    打印 dry-run 汇总信息。

    这里的目的不是“炫日志”，而是让操作者在真正写库前，
    能直观看到这次任务到底会处理什么。
    """

    print(f"Target table: {table_name}")
    print(f"Input path: {input_path}")
    print(f"Chunk files: {summary['file_count']}")
    print(f"Total rows: {summary['total_rows']}")
    print(f"Columns: {', '.join(summary['all_columns']) if summary['all_columns'] else '(none)'}")
    print(f"Batch size: {batch_size}")
    print(f"Primary key columns: {', '.join(pk_columns)}")
    print(f"JSON columns: {', '.join(json_columns) if json_columns else '(none)'}")
    print(f"Empty primary key rows: {summary['empty_pk_rows']}")
    print(f"Duplicate primary key rows inside input: {summary['duplicate_pk_rows']}")
    print(f"Invalid JSON rows: {summary['invalid_json_rows']}")

    # 如果有 JSON 错误示例，就打印出来，方便定位问题
    if summary["invalid_json_examples"]:
        print("Invalid JSON examples:")
        for example in summary["invalid_json_examples"]:
            print(
                f"  file={example['file']} row={example['row']} column={example['column']}: "
                f"{example['error']} | value={example['value']}"
            )


def is_retryable_connection_error(exc: Exception) -> bool:
    """
    判断某个异常是否属于“可重试的连接类错误”。

    这里的策略很保守：
    - 只对明显的连接问题重试
    - 不对其他数据库逻辑错误重试

    这样做的原因：
    - 如果是数据本身有问题，重试没有意义
    - 如果无限重试，反而可能掩盖风险
    """

    # 先把异常文本转成小写，做关键字判断
    message = str(exc).lower()

    retryable_keywords = [
        "server has gone away",
        "lost connection",
        "connection reset",
        "connection refused",
        "not connected",
        "already closed",
        "interfaceerror",
        "operationalerror",
    ]

    # 文本中命中任意关键字，就视为连接类问题
    if any(keyword in message for keyword in retryable_keywords):
        return True

    # 再进一步，如果环境里有 pymysql，则尝试用异常类型判断
    try:
        import pymysql

        if isinstance(exc, (pymysql.err.InterfaceError, pymysql.err.OperationalError)):
            return True
    except Exception:
        # 如果这里导入失败或判断失败，不影响主流程
        pass

    return False


def build_insert_sql(table_name: str, columns: list[str]) -> str:
    """
    构造 INSERT SQL。

    这里只做最简单的 plain INSERT，不做 upsert。
    原则是：
    - 表名用反引号包裹
    - 列名用反引号包裹
    - 值使用参数占位符 %s
    """

    sql_columns = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO `{table_name}` ({sql_columns}) VALUES ({placeholders})"


def convert_rows_to_values(columns: list[str], rows: list[dict[str, str | None]]) -> list[tuple]:
    """
    把行字典转换成 executemany 需要的参数元组列表。

    规则：
    - 空字符串 -> None
    - 其他值 -> 原样保留

    这样做的原因：
    - 让数据库自己处理 NULL
    - 避免把空字符串误插成有意义的文本值
    """

    values: list[tuple] = []

    for row in rows:
        values.append(
            tuple(None if row.get(column) == "" else row.get(column) for column in columns)
        )

    return values


def insert_one_batch(table_name: str, columns: list[str], rows: list[dict[str, str | None]]) -> None:
    """
    插入一个 batch。

    注意这里故意不复用外部连接。
    这个函数的职责只有一件事：建连、执行、提交、断连。

    这样做的原因：
    - 短效账号在真实环境里更稳
    - 每个 batch 自成一个很小的独立事务
    - 出问题时更容易定位
    """

    from src.database import DatabaseManager

    # 每个 batch 自己创建连接管理器
    db = DatabaseManager()

    try:
        # 建立连接
        if not db.connect():
            raise ConnectionError("Database connection failed.")

        # 构造 SQL
        sql = build_insert_sql(table_name, columns)

        # 准备参数
        values = convert_rows_to_values(columns, rows)

        # 执行批量插入
        db.executemany(sql, values)

    finally:
        # 无论成功还是失败，都主动断开连接
        db.disconnect()


def insert_one_batch_with_retry(table_name: str, columns: list[str], rows: list[dict[str, str | None]]) -> None:
    """
    对单个 batch 做一次“最多重试 1 次”的插入。

    这里只对连接类问题重试 1 次，不做无限重试。
    原因：
    - 无限重试会掩盖现场问题
    - 安全评审更容易接受“失败就停止并明确报错”
    """

    try:
        # 第一次尝试
        insert_one_batch(table_name, columns, rows)

    except Exception as exc:
        # 不是连接类错误，直接往外抛
        if not is_retryable_connection_error(exc):
            raise

        print("[WARN] Batch insert failed because of a connection problem. Retrying this batch once.")

        try:
            # 第二次尝试，也是最后一次
            insert_one_batch(table_name, columns, rows)
        except Exception as retry_exc:
            # 第二次还失败，就直接停止
            raise RuntimeError(
                "Batch insert failed again after one retry. The script stopped to avoid hidden partial failures."
            ) from retry_exc


def main() -> int:
    """
    脚本主入口。

    主流程分成两大段：
    1. dry-run 校验阶段
    2. 正式插入阶段

    更细一点的顺序是：
    1. 解析参数
    2. 校验表名
    3. 校验 skip-db-check 和 dry-run 的组合是否合法
    4. 确定输入路径
    5. 读取表配置
    6. 列出要处理的 CSV 文件
    7. 若不跳过数据库检查，则连接数据库获取表结构/主键/JSON 列
    8. 做 dry-run 检查
    9. 如果 dry-run 模式，直接结束
    10. 否则按文件、按 batch 逐步插入
    """

    args = parse_args()

    # 延迟导入项目内部模块
    from src.chunk_csv import list_chunk_files
    from src.database import DatabaseManager
    from src.profile_store import get_table_profile

    # -------------------------------------------------------------
    # 第一步：校验表名
    # -------------------------------------------------------------
    try:
        table_name = validate_table_name(args.table)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    # -------------------------------------------------------------
    # 第二步：参数组合合法性检查
    # -------------------------------------------------------------
    # skip-db-check 只允许和 dry-run 一起用
    # 因为正式插入必须知道真实表结构和数据库信息，不能完全跳过数据库检查
    if args.skip_db_check and not args.dry_run:
        print("[ERROR] --skip-db-check can only be used together with --dry-run.")
        return 1

    # -------------------------------------------------------------
    # 第三步：确定输入路径
    # -------------------------------------------------------------
    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))

    # 如果用户传了 --input，就按指定路径处理
    # 否则默认使用 data/<table>/chunks
    input_path = Path(args.input) if args.input else csv_base_dir / table_name / "chunks"

    if not input_path.exists():
        print(f"[ERROR] Input path not found: {input_path}")
        return 1

    # -------------------------------------------------------------
    # 第四步：读取表配置和 batch size
    # -------------------------------------------------------------
    try:
        profile = get_table_profile(args.profile_file, table_name)
        batch_size = resolve_batch_size(args, profile)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    # 这里先初始化一些后面会用到的变量
    db = None
    json_columns: list[str] = []
    table_columns: list[str] | None = None

    try:
        # ---------------------------------------------------------
        # 第五步：列出所有待处理的 CSV 文件
        # ---------------------------------------------------------
        csv_files = list_chunk_files(input_path)
        if not csv_files:
            print(f"[ERROR] No CSV files found in input path: {input_path}")
            return 1

        # ---------------------------------------------------------
        # 第六步：决定是否连接数据库做真实检查
        # ---------------------------------------------------------
        if not args.skip_db_check:
            # 连接数据库
            db = DatabaseManager()
            if not db.connect():
                print("[ERROR] Database connection failed.")
                return 1

            # 读取真实表列
            table_columns = db.get_column_names(table_name)

            # 解析主键列
            pk_columns, pk_source = resolve_primary_key_columns(
                args, profile, db, table_name, table_columns
            )

            # 解析 JSON 列
            json_columns = resolve_json_columns(args, profile, db, table_name)

        else:
            # skip-db-check 场景：
            # 不连库，只基于 CSV 本身和配置进行 dry-run
            csv_columns = get_first_csv_column(csv_files)

            # 主键列如果没有明确配置，就回退到 CSV 第一列
            pk_columns, pk_source = resolve_primary_key_columns(
                args, profile, None, table_name, csv_columns
            )

            # JSON 列只从命令行和 profile 中拿
            json_columns = sorted(
                set(parse_column_list(args.json_cols)) |
                set(get_profile_list(profile, "json_columns"))
            )

        # ---------------------------------------------------------
        # 第七步：执行 dry-run 检查
        # ---------------------------------------------------------
        summary = validate_csv_files(csv_files, pk_columns, json_columns, table_columns)

        # 打印 dry-run 摘要
        print_dry_run_summary(
            table_name,
            input_path,
            batch_size,
            pk_columns,
            json_columns,
            summary,
        )
        print(f"Primary key source: {pk_source}")

        # 主键为空或重复，直接失败
        if summary["empty_pk_rows"] > 0 or summary["duplicate_pk_rows"] > 0:
            print("[ERROR] Dry-run failed because the input contains invalid primary key values.")
            return 1

        # JSON 非法，也直接失败
        if summary["invalid_json_rows"] > 0:
            print("[ERROR] Dry-run failed because the input contains invalid JSON values.")
            return 1

        # 如果只是 dry-run，到这里就结束，不写库
        if args.dry_run:
            print("[OK] Dry-run passed. No rows were inserted.")
            return 0

        # ---------------------------------------------------------
        # 第八步：正式插入
        # ---------------------------------------------------------
        total_rows = summary["total_rows"]
        inserted_rows = 0
        columns = summary["all_columns"]

        # 正式插入阶段不复用长连接。
        # 每个 batch 单独建连 / 提交 / 断连，这样即使账号很短效，也只会影响当前小批次。
        for file_path in csv_files:
            # 对当前 chunk 重新读取并规范化
            _, normalized_rows = normalize_rows_for_insert(file_path, json_columns)

            # 再按 batch-size 分批插入
            for start in range(0, len(normalized_rows), batch_size):
                batch_rows = normalized_rows[start : start + batch_size]

                # 单个 batch 插入，带 1 次重试
                insert_one_batch_with_retry(table_name, columns, batch_rows)

                inserted_rows += len(batch_rows)
                print(f"[OK] Inserted {inserted_rows}/{total_rows} rows")

        print(f"[DONE] Insert completed: {inserted_rows} rows inserted into {table_name}")
        return 0

    except Exception as exc:
        print(f"[ERROR] Insert failed: {exc}")
        return 1

    finally:
        # 外层这个 db 只用于前面的元信息检查，
        # 不参与正式 batch 插入。
        # 无论成功失败，都在这里断开。
        if db is not None:
            db.disconnect()


# 标准 Python 脚本入口
if __name__ == "__main__":
    sys.exit(main())