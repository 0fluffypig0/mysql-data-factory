#!/usr/bin/env python3
"""
基于单条模板记录分块生成 CSV。

这个脚本是 V1.1 的核心生成步骤，设计目标很明确：
1. 模板文件默认只使用 1 条记录。
2. 生成时只修改主键列和必要唯一键列。
3. 其他字段一律原样照抄，包括 JSON 字段。
4. 一次只生成一个 chunk，避免在堡垒机上一次性占用过多内存。

输入：
- template.csv
- 目标总行数
- 表配置文件 / 环境变量 / 数据库扫描得到的主键信息

输出：
- data/<table>/chunks/chunk_000001.csv
- data/<table>/chunks/chunk_000002.csv
- ...

适用场景：
- 已经找到一条“好的模板数据”
- 只需要改主键和必要唯一键
- 希望在堡垒机上稳定生成大批量数据，但不想一次性生成超大 CSV
"""

# 这行的作用：
# 让类型注解延迟求值。
# 对业务逻辑没有影响，主要是为了让类型注解写起来更自然、更兼容。
from __future__ import annotations

# argparse：解析命令行参数，例如 --table、--rows、--chunk-size 等
import argparse

# math：这里主要用于 math.ceil()，计算总共需要几个 chunk 文件
import math

# os：读取环境变量，例如 TARGET_TABLE、CSV_BASE_DIR、DEFAULT_CHUNK_SIZE 等
import os

# re：用正则校验表名，以及判断某个值是否“像整数”
import re

# sys：用于两件事
# 1. 把项目根目录加入 sys.path，确保能导入 src 模块
# 2. 在脚本末尾用 sys.exit(main()) 返回退出码
import sys

# Path：处理路径比字符串更清楚，适合做路径拼接与目录创建
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# 当前文件路径形如：
#   <项目根目录>/scripts/expand_rows.py
# parents[1] 对应项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 把项目根目录加入 sys.path，确保后面可以导入：
# - src.chunk_csv
# - src.database
# - src.profile_store
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------
# 安全与基础校验正则
# ---------------------------------------------------------------------
# 表名只允许：
# - 字母
# - 数字
# - 下划线
# 这样做是为了避免非法表名进入 SQL 相关逻辑。
TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")

# 判断一个值是否“像整数”
# 例如：
# "123" -> True
# "-001" -> True
# "ABC" -> False
INTEGER_RE = re.compile(r"^-?\d+$")


def resolve_env_file(env_file: str) -> Path:
    """
    把传入的 env 文件路径解析成绝对路径。

    规则：
    - 如果是绝对路径，直接使用
    - 如果是相对路径，默认相对于项目根目录
    """

    # 先把字符串变成 Path 对象
    env_path = Path(env_file)

    # 如果不是绝对路径，则拼到项目根目录下面
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    """
    尝试加载 .env 文件。

    这里故意写成“能加载就加载，加载不了也不直接崩”：
    - 有些极简环境可能没有 python-dotenv
    - 这时仍然可以靠系统环境变量运行

    注意：
    - override=True：env 文件里的值覆盖已有环境变量
    - encoding='utf-8-sig'：兼容 Windows 可能带 BOM 的文件
    """

    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        # 如果没装 python-dotenv，就不在这里报错
        return

    load_dotenv(resolve_env_file(env_file), override=True, encoding="utf-8-sig")


def parse_column_list(raw_value: str | None) -> list[str]:
    """
    把逗号分隔的列名字符串解析成列表。

    例如：
    "id,code,created_at"
    -> ["id", "code", "created_at"]

    空值时返回空列表。
    """

    if not raw_value:
        return []

    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    和其他脚本保持一致：
    1. 先预解析 --env-file
    2. 加载 env 文件
    3. 再正式解析全部参数

    这样后面的默认值就可以从 env 里读取。
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
    parser = argparse.ArgumentParser(description="Generate chunk CSV files from one template row.")

    # 运行配置文件路径
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )

    # 目标表名，默认取 TARGET_TABLE
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))

    # 表配置文件路径，默认取 config/table_profiles.json
    parser.add_argument(
        "--profile-file",
        default=os.getenv("TABLE_PROFILE_PATH", "config/table_profiles.json"),
        help="Path to the table profile JSON file.",
    )

    # 模板文件路径
    # 如果不传，后面会默认取 data/<table>/template.csv
    parser.add_argument("--input", help="Path to template.csv.")

    # 输出目录
    # 如果不传，后面会默认用 data/<table>/chunks/
    parser.add_argument("--output-dir", help="Directory for generated chunk CSV files.")

    # 需要总共生成多少条数据
    # 这是核心必填参数
    parser.add_argument("--rows", type=int, required=True, help="Total number of generated rows.")

    # 主键列，可手工指定
    # 如果不指定，后面会按：
    # 命令行 -> 表配置 -> env -> 数据库扫描 -> 第一列兜底
    parser.add_argument("--pk-cols")

    # 唯一键列，可手工指定
    parser.add_argument("--unique-cols")

    # JSON 列，可手工指定
    parser.add_argument("--json-cols")

    # chunk 大小
    # 例如 5000 或 10000
    parser.add_argument(
        "--chunk-size",
        type=int,
        help="How many rows one chunk file should contain. Maximum is 10000.",
    )

    return parser.parse_args()


def validate_table_name(table_name: str) -> str | None:
    """
    校验表名是否合法。

    这里和导出脚本保持一致：
    - None 或空字符串时返回 None
    - 非空时必须满足“字母数字下划线”规则
    """

    if table_name is None or table_name == "":
        return None

    if not TABLE_NAME_RE.match(table_name):
        raise ValueError("Table name may only contain letters, numbers, and underscores.")

    return table_name


def is_integer_like(value: object) -> bool:
    """
    判断某个值是否“像整数”。

    注意：
    - None -> False
    - "00123" -> True
    - "-5" -> True
    - "ABC123" -> False
    """

    if value is None:
        return False

    return INTEGER_RE.match(str(value).strip()) is not None


def format_integer_like(new_value: int, template_value: object) -> str:
    """
    按模板值的“外观”格式化新的整数值。

    设计目的：
    - 如果模板主键是有前导零的，例如 000123
    - 新生成的值也尽量保持同样宽度
    - 如果模板是负数，也尽量保留符号形式

    示例：
    template_value = "000123", new_value = 45
    -> "000045"
    """

    # 先把模板值转成去空格后的字符串
    raw_text = "" if template_value is None else str(template_value).strip()

    # 处理负数格式，例如 "-00012"
    if raw_text.startswith("-"):
        raw_digits = raw_text[1:]

        # 如果原始负数去掉符号后长度大于 1 且以 0 开头，
        # 则按相同宽度补零
        if len(raw_digits) > 1 and raw_digits.startswith("0"):
            return f"-{abs(new_value):0{len(raw_digits)}d}"

        # 否则直接返回普通整数形式
        return str(new_value)

    # 处理正数前导零，例如 "000123"
    if len(raw_text) > 1 and raw_text.startswith("0"):
        return str(new_value).zfill(len(raw_text))

    # 普通情况，直接转字符串
    return str(new_value)


def increment_key_value(template_value: object, sequence_index: int, start_value: int | None) -> str:
    """
    生成新的主键值或唯一键值。

    设计原则非常朴素：
    - 只改主键和必要唯一键
    - 不改其他字段
    - 如果是整数型，就递增
    - 如果是字符串型，就加顺序后缀

    参数说明：
    - template_value：模板里的原始值
    - sequence_index：当前是第几条生成记录（从 0 开始）
    - start_value：如果数据库已经扫描到了安全起始值，就从这里开始
    """

    raw_text = "" if template_value is None else str(template_value)

    # 如果模板本身是空字符串，就直接返回空字符串
    if raw_text == "":
        return raw_text

    # 如果已经有明确的起始值
    if start_value is not None:
        # 整数型模板值：按起始值 + 序号生成
        if is_integer_like(raw_text):
            return format_integer_like(start_value + sequence_index, template_value)

        # 字符串型模板值：在原值后追加 6 位序号
        return f"{raw_text}_{start_value + sequence_index:06d}"

    # 如果没有起始值，但模板值本身是整数
    # 就直接在模板值基础上递增
    if is_integer_like(raw_text):
        return format_integer_like(int(raw_text) + sequence_index, template_value)

    # 非整数型且没有数据库起始值时，
    # 最简单规则：原值 + 序号后缀
    return f"{raw_text}_{sequence_index + 1:06d}"


def get_profile_list(profile: dict | None, key_name: str) -> list[str]:
    """
    从表配置 profile 中读取列表型字段。

    例如：
    - primary_key_columns
    - unique_key_columns
    - json_columns
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
    - default_chunk_size
    - default_insert_batch_size

    如果没有、为空或不是合法整数，则返回 None。
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


def resolve_primary_key_columns(
    args: argparse.Namespace,
    profile: dict | None,
    template_fieldnames: list[str],
    db,
    table_name: str | None,
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

    # 1. 命令行显式指定
    if parse_column_list(args.pk_cols):
        return parse_column_list(args.pk_cols), "command_or_env"

    # 2. 表配置文件
    profile_columns = get_profile_list(profile, "primary_key_columns")
    if profile_columns:
        return profile_columns, "table_profile"

    # 3. 环境变量
    env_columns = parse_column_list(os.getenv("PRIMARY_KEY_COLUMNS"))
    if env_columns:
        return env_columns, "env"

    # 4. 数据库扫描主键
    if db is not None and table_name:
        database_columns = db.get_primary_key_columns(table_name)
        if database_columns:
            return database_columns, "database_scan"

    # 5. 如果以上都拿不到，就把模板 CSV 第一列当主键
    # 这是 V1.1 里明确约定的最简单兜底逻辑
    if template_fieldnames:
        return [template_fieldnames[0]], "first_column_fallback"

    raise ValueError("Could not determine primary key columns.")


def resolve_unique_key_columns(args: argparse.Namespace, profile: dict | None, pk_columns: list[str]) -> list[str]:
    """
    解析必要唯一键列。

    原则：
    - 命令行 > profile > env
    - 已经是主键列的，不再重复放进唯一键列
    """

    configured_columns = parse_column_list(args.unique_cols)
    if configured_columns:
        return [column for column in configured_columns if column not in pk_columns]

    profile_columns = get_profile_list(profile, "unique_key_columns")
    if profile_columns:
        return [column for column in profile_columns if column not in pk_columns]

    env_columns = parse_column_list(os.getenv("UNIQUE_KEY_COLUMNS"))
    return [column for column in env_columns if column not in pk_columns]


def resolve_json_columns(args: argparse.Namespace, profile: dict | None) -> list[str]:
    """
    解析 JSON 列列表。

    原则：
    - 命令行 > profile > env
    - 这里只负责“哪些列是 JSON”
    - 不修改 JSON 内容，只在后续逻辑中原样复制
    """

    configured_columns = parse_column_list(args.json_cols)
    if configured_columns:
        return configured_columns

    profile_columns = get_profile_list(profile, "json_columns")
    if profile_columns:
        return profile_columns

    return parse_column_list(os.getenv("JSON_COLUMNS"))


def resolve_chunk_size(args: argparse.Namespace, profile: dict | None) -> int:
    """
    解析 chunk 大小。

    优先级：
    1. 命令行 --chunk-size
    2. profile 中的 default_chunk_size
    3. 环境变量 DEFAULT_CHUNK_SIZE
    4. 默认 5000

    最终还会调用 ensure_chunk_size() 做合法性约束，
    确保不会超过系统允许的上限（例如 10000）。
    """

    raw_value = args.chunk_size

    if raw_value is None:
        raw_value = get_profile_int(profile, "default_chunk_size")

    if raw_value is None:
        raw_value = int(os.getenv("DEFAULT_CHUNK_SIZE", "5000"))

    from src.chunk_csv import ensure_chunk_size

    return ensure_chunk_size(int(raw_value))


def ensure_required_columns_exist(
    template_fieldnames: list[str],
    pk_columns: list[str],
    unique_columns: list[str],
    json_columns: list[str],
) -> None:
    """
    检查模板 CSV 是否包含运行所需的全部关键列。

    需要存在的列包括：
    - 主键列
    - 唯一键列
    - JSON 列

    如果配置中提到的列在模板里不存在，就直接报错。
    """

    required_columns = pk_columns + unique_columns + json_columns
    missing_columns = [column for column in required_columns if column not in template_fieldnames]

    if missing_columns:
        raise ValueError(f"Configured columns not found in template CSV: {missing_columns}")


def query_max_value(db, table_name: str, column_name: str) -> int | None:
    """
    查询数据库中某一列的最大值。

    典型用途：
    - 主键是整数型时，从 max(pk)+1 开始生成
    - 唯一键是整数型时，也可从最大值后继续递增
    """

    rows = db.query(f"SELECT MAX(`{column_name}`) FROM `{table_name}`")

    if not rows:
        return None

    value = rows[0][0]

    if value is None:
        return None

    if is_integer_like(value):
        return int(str(value))

    return None


def escape_like_value(raw_value: str) -> str:
    """
    对 LIKE 查询中的特殊字符做转义。

    需要转义的典型字符：
    - 反斜杠 \
    - 百分号 %
    - 下划线 _

    这样做是为了让“前缀匹配统计”更准确。
    """

    return raw_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def query_string_suffix_start(db, table_name: str, column_name: str, template_value: str) -> int:
    """
    为字符串型唯一键找到“后缀起点”。

    例如模板值是 `SMOKE002`，数据库里已经存在：
    - `SMOKE002`
    - `SMOKE002_000001`
    - `SMOKE002_000002`

    那么这里就从 3 开始，后续生成：
    - `SMOKE002_000003`

    这样做的目标不是追求复杂规则，而是解决最常见、最容易解释的“字符串唯一键重复”问题。
    """

    # 先转义模板值，避免 LIKE 匹配时把 % 和 _ 当作通配符
    escaped_value = escape_like_value(template_value)

    # 匹配形如：
    #   模板值_任意后缀
    like_pattern = f"{escaped_value}\\_%"

    # 查询数据库中已经存在多少条：
    # 1. 完全等于模板值的
    # 2. 或者以“模板值_”开头的
    rows = db.query(
        f"""
        SELECT COUNT(*)
        FROM `{table_name}`
        WHERE `{column_name}` = %s
           OR `{column_name}` LIKE %s ESCAPE '\\\\'
        """,
        (template_value, like_pattern),
    )

    if not rows:
        return 1

    count_value = int(rows[0][0])

    # 如果一个都没有，就从 1 开始
    if count_value <= 0:
        return 1

    # 如果已有 N 个，则新生成从 N 开始继续编号
    return count_value


def resolve_numeric_start_values(
    db,
    table_name: str | None,
    template_row: dict[str, str],
    key_columns: list[str],
) -> dict[str, int | None]:
    """
    为主键和必要唯一键计算起始值。

    规则非常简单：
    - 整数型列：从数据库当前最大值 + 1 开始
    - 字符串型列：从数据库中已有同前缀记录数量开始追加后缀
    - 其他字段：不参与这一步
    """

    # 最终返回：
    # {
    #   "id": 1004,
    #   "customer_code": 3,
    #   ...
    # }
    start_values: dict[str, int | None] = {}

    for column in key_columns:
        template_value = template_row.get(column)

        # 默认先给 None，表示“还没确定”
        start_values[column] = None

        # 如果模板里的值不是整数型
        if not is_integer_like(template_value):
            # 没有数据库连接或没有表名时，就没法扫描数据库
            if db is None or not table_name:
                continue

            # 对字符串型唯一键，去查数据库里已有多少同前缀值
            start_values[column] = query_string_suffix_start(db, table_name, column, str(template_value))
            continue

        # 如果是整数型，但没有数据库连接，就没法查 max 值
        if db is None or not table_name:
            continue

        # 查数据库当前最大值
        max_value = query_max_value(db, table_name, column)

        # 如果查到了，就从最大值 + 1 开始
        if max_value is not None:
            start_values[column] = max_value + 1

    return start_values


def build_generated_row(
    template_row: dict[str, str],
    pk_columns: list[str],
    unique_columns: list[str],
    start_values: dict[str, int | None],
    sequence_index: int,
) -> dict[str, str]:
    """
    基于单条模板构造一条新记录，只改主键和必要唯一键。

    这是 V1.1 生成逻辑的核心原则：
    - 主键改
    - 必要唯一键改
    - 其他字段全部照抄模板

    这样最朴素，也最容易讲清楚。
    """

    # 先复制一整行模板，默认所有字段都继承模板值
    generated_row = dict(template_row)

    # 主键列逐个替换
    for column in pk_columns:
        generated_row[column] = increment_key_value(
            template_row.get(column),
            sequence_index,
            start_values.get(column),
        )

    # 必要唯一键列逐个替换
    for column in unique_columns:
        generated_row[column] = increment_key_value(
            template_row.get(column),
            sequence_index,
            start_values.get(column),
        )

    return generated_row


def main() -> int:
    """
    脚本主入口。

    主要流程非常直接：
    1. 解析参数
    2. 读取模板 CSV
    3. 读取表配置
    4. 确定主键 / 唯一键 / JSON 列 / chunk size
    5. 检查模板列是否完整
    6. 计算主键和唯一键的起始值
    7. 逐 chunk 生成 CSV 文件
    8. 输出生成结果
    """

    args = parse_args()

    # 延迟导入项目内部模块
    # 这样只看 --help 时，不会过早依赖数据库层和 CSV 工具层
    from src.chunk_csv import build_chunk_file_path, read_template_csv, resolve_chunk_dir, write_rows_to_csv
    from src.database import DatabaseManager
    from src.profile_store import get_table_profile

    # rows 必须大于 0
    if args.rows <= 0:
        print("[ERROR] --rows must be greater than 0.")
        return 1

    # -------------------------------------------------------------
    # 第一步：校验表名
    # -------------------------------------------------------------
    try:
        table_name = validate_table_name(args.table)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    # -------------------------------------------------------------
    # 第二步：确定模板 CSV 路径
    # -------------------------------------------------------------
    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))

    # 如果表名为空，目录名兜底用 "table"
    table_folder_name = table_name or "table"

    # 如果用户传了 --input，就用指定路径
    # 否则默认使用 data/<table>/template.csv
    input_path = Path(args.input) if args.input else csv_base_dir / table_folder_name / "template.csv"

    # 模板文件不存在就直接报错
    if not input_path.exists():
        print(f"[ERROR] Template CSV not found: {input_path}")
        return 1

    # -------------------------------------------------------------
    # 第三步：读取模板 CSV
    # -------------------------------------------------------------
    try:
        template_fieldnames, template_rows = read_template_csv(input_path)
    except Exception as exc:
        print(f"[ERROR] Failed to read template CSV: {exc}")
        return 1

    # 模板 CSV 为空也不能继续
    if not template_rows:
        print("[ERROR] Template CSV is empty.")
        return 1

    # V1.1 只主推单模板模式
    # 如果模板里有多条，只给警告，并且后面只用第一条
    if len(template_rows) > 1:
        print("[WARN] Template CSV contains more than one row. V1.1 only uses the first row as template.")

    # 只取第一条作为模板
    template_row = template_rows[0]

    # 默认还没有数据库连接
    db = None

    try:
        # ---------------------------------------------------------
        # 第四步：读取表配置
        # ---------------------------------------------------------
        profile = get_table_profile(args.profile_file, table_name or "")

        # ---------------------------------------------------------
        # 第五步：如果有表名，则尝试连接数据库
        # ---------------------------------------------------------
        # 这里连接数据库的目的主要是：
        # - 扫描主键
        # - 查询最大值
        # - 计算字符串唯一键后缀起点
        if table_name:
            probe_db = DatabaseManager()
            if probe_db.connect():
                db = probe_db

        # ---------------------------------------------------------
        # 第六步：解析关键列与 chunk 大小
        # ---------------------------------------------------------
        pk_columns, pk_source = resolve_primary_key_columns(args, profile, template_fieldnames, db, table_name)
        unique_columns = resolve_unique_key_columns(args, profile, pk_columns)
        json_columns = resolve_json_columns(args, profile)
        chunk_size = resolve_chunk_size(args, profile)

        # 检查模板 CSV 是否含有这些关键列
        ensure_required_columns_exist(template_fieldnames, pk_columns, unique_columns, json_columns)

        # 计算主键/唯一键的新起始值
        start_values = resolve_numeric_start_values(db, table_name, template_row, pk_columns + unique_columns)

        # ---------------------------------------------------------
        # 第七步：确定 chunk 输出目录
        # ---------------------------------------------------------
        if args.output_dir:
            chunk_dir = Path(args.output_dir)
        else:
            chunk_dir = resolve_chunk_dir(csv_base_dir, table_folder_name)

        # 确保目录存在
        chunk_dir.mkdir(parents=True, exist_ok=True)

        # ---------------------------------------------------------
        # 第八步：计算需要几个 chunk
        # ---------------------------------------------------------
        total_chunks = math.ceil(args.rows / chunk_size)

        # 已生成总行数
        generated_total = 0

        # 全局序号，从 0 开始递增
        # 不会每个 chunk 重新归零
        global_sequence_index = 0

        # 输出本次任务的摘要信息，便于人工确认
        print(f"Template file: {input_path}")
        print(f"Primary key columns: {pk_columns} ({pk_source})")
        print(f"Unique key columns: {unique_columns if unique_columns else '(none)'}")
        print(f"JSON columns: {json_columns if json_columns else '(none)'}")
        print(f"Chunk size: {chunk_size}")
        print(f"Total rows to generate: {args.rows}")
        print(f"Chunk output directory: {chunk_dir}")

        # ---------------------------------------------------------
        # 第九步：逐 chunk 生成 CSV
        # ---------------------------------------------------------
        # 这里采用“一个 chunk 一个文件”的方式，而不是一次性生成一个巨大的 generated.csv。
        # 原因很简单：堡垒机内存通常紧张，小文件更稳，也更利于失败后排查和重跑。
        for chunk_index in range(1, total_chunks + 1):
            # 还剩多少行没生成
            remaining_rows = args.rows - generated_total

            # 当前这个 chunk 要生成多少行
            current_chunk_rows = min(chunk_size, remaining_rows)

            # 暂存当前 chunk 的数据行
            rows_to_write: list[dict[str, str]] = []

            # 逐行构造当前 chunk 的数据
            for _ in range(current_chunk_rows):
                generated_row = build_generated_row(
                    template_row,
                    pk_columns,
                    unique_columns,
                    start_values,
                    global_sequence_index,
                )
                rows_to_write.append(generated_row)

                # 更新总进度
                generated_total += 1
                global_sequence_index += 1

            # 先按默认规则生成文件路径
            chunk_file_path = build_chunk_file_path(csv_base_dir, table_folder_name, chunk_index)

            # 如果用户显式指定了输出目录，就把文件落到那个目录下
            if args.output_dir:
                chunk_file_path = chunk_dir / chunk_file_path.name

            # 把当前 chunk 写成 CSV 文件
            write_rows_to_csv(chunk_file_path, template_fieldnames, rows_to_write)

            # 输出 chunk 成功信息
            print(f"[OK] Generated chunk {chunk_index}/{total_chunks}: {chunk_file_path} ({current_chunk_rows} rows)")

        # 所有 chunk 生成完成
        print(f"[DONE] Generated {generated_total} rows into {total_chunks} chunk file(s).")
        return 0

    except Exception as exc:
        # 统一错误出口，便于用户看到清晰错误提示
        print(f"[ERROR] Expansion failed: {exc}")
        return 1

    finally:
        # 无论成功失败，都主动断开数据库连接
        # 这有助于后续短连接策略，也更适合短效账号场景
        if db is not None:
            db.disconnect()


# 标准 Python 脚本入口
if __name__ == "__main__":
    sys.exit(main())