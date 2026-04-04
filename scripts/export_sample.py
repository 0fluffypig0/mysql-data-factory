#!/usr/bin/env python3
"""
导出单表样本或单条模板记录。

这个脚本服务两个场景：
1. 先按 limit 导出少量样本，供人工挑选模板。
2. 已经知道某条记录的主键值时，按主键精确导出这一条记录作为模板。

输入：
- .env 或 --env-file 指定的环境配置
- 目标表名
- 可选的主键值

输出：
- sample.csv 或 template.csv

设计原则：
- 逻辑尽量展开，不做复杂抽象。
- 优先读取表配置文件。
- 没有配置时，先扫描数据库主键。
- 如果数据库也无法给出主键，就退回到“第一列是主键”这个最简单兜底规则。
"""

# 这一行的作用：
# 让类型注解在运行时延迟解析。
# 好处是：即使某些类型在定义时还没有真正导入，也不会立即报错。
# 对业务逻辑没有影响，主要是为了让类型注解写起来更自然。
from __future__ import annotations

# argparse：用于解析命令行参数，例如 --table、--pk-value、--env-file 等
import argparse

# csv：用于把查询结果写成 CSV 文件
import csv

# json：用于处理数据库中的 JSON 字段，把它们规范化后再写进 CSV
import json

# os：用于读取环境变量，例如 TARGET_TABLE、EXPORT_SAMPLE_LIMIT、JSON_COLUMNS 等
import os

# re：用于正则校验表名是否合法，防止非法表名进入 SQL 字符串
import re

# sys：这里主要用于两件事：
# 1. 把项目根目录加入 sys.path，确保可以导入 src 下的模块
# 2. 在文件结尾用 sys.exit(main()) 返回退出码
import sys

# Path：比传统字符串路径更安全、更清楚，适合做路径拼接与判断
from pathlib import Path


# ---------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------
# __file__ 是当前脚本自身路径。
# resolve() 会把它转换成绝对路径。
# parents[1] 表示：
# - 当前文件在 scripts/export_sample.py
# - parents[0] 是 scripts/
# - parents[1] 是项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 为了保证脚本在任何位置被调用时，都能成功 import 项目内模块，
# 这里把项目根目录加入 sys.path。
# 这样后面就能导入 src.database、src.profile_store。
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------
# 安全校验：表名正则
# ---------------------------------------------------------------------
# 这里限制表名只能由：
# - 大写字母
# - 小写字母
# - 数字
# - 下划线
# 组成。
#
# 这样做的目的是避免表名中混入危险字符，
# 因为后面 SQL 会把表名拼接进字符串。
TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def resolve_env_file(env_file: str) -> Path:
    """
    把用户传入的 env 文件路径解析成绝对路径。

    设计目的：
    - 用户可以传相对路径，例如 .env.smoke
    - 也可以传绝对路径
    - 最终统一得到一个明确可访问的 Path 对象
    """

    # 先把传入字符串转成 Path 对象
    env_path = Path(env_file)

    # 如果用户传的是相对路径，就默认认为它相对于项目根目录
    # 例如：
    #   --env-file .env.smoke
    # 会被解析成：
    #   <项目根目录>/.env.smoke
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    # 返回最终解析后的路径
    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    """
    尝试加载 .env 文件。

    这里故意写成“尽量加载，但加载失败时不直接崩”，原因是：
    - 某些极简环境下，python-dotenv 可能没有安装
    - 这时脚本仍然可以依赖系统环境变量运行

    注意：
    - override=True 表示 env 文件中的值会覆盖已有环境变量
    - encoding='utf-8-sig' 兼容 Windows 下可能带 BOM 的 .env 文件
    """

    try:
        # 延迟导入 python-dotenv
        # 这样只有真的需要加载 .env 时才尝试导入
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        # 如果环境里没有安装 python-dotenv，就直接返回
        # 不在这里报错，是为了兼容“只靠系统环境变量运行”的场景
        return

    # 正式加载 env 文件
    load_dotenv(
        resolve_env_file(env_file),
        override=True,
        encoding="utf-8-sig",
    )


def parse_column_list(raw_value: str | None) -> list[str]:
    """
    把逗号分隔的列名字符串解析成列表。

    例如：
    "id,code,created_at"
    -> ["id", "code", "created_at"]

    为空时返回空列表。
    """

    # 如果原始值为空、None、空字符串，直接返回空列表
    if not raw_value:
        return []

    # split(",") 后逐个 strip() 去掉前后空格
    # 并且过滤掉空项
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    这里分成两段解析：
    1. 先只解析 --env-file
    2. 先加载对应 env 文件
    3. 再正式解析全部参数

    这样做的好处是：
    - 后面的参数默认值可以来自 env 文件
    - 例如 --table 默认可取 TARGET_TABLE
    - --limit 默认可取 EXPORT_SAMPLE_LIMIT
    """

    # -----------------------------------------------------------------
    # 第一次“预解析”：只为了拿到 --env-file
    # -----------------------------------------------------------------
    # add_help=False 的意思是：
    # 这里只是一个临时的小 parser，不负责完整 help 输出
    env_parser = argparse.ArgumentParser(add_help=False)

    # 定义 --env-file 参数，默认值是 .env
    env_parser.add_argument("--env-file", default=".env")

    # parse_known_args()：
    # - 只解析自己认识的参数
    # - 把其余未知参数先留着
    env_args, _ = env_parser.parse_known_args()

    # 先加载 env 文件
    # 这样后面 parser.add_argument(default=os.getenv(...)) 时就能拿到 env 中的值
    maybe_load_dotenv(env_args.env_file)

    # -----------------------------------------------------------------
    # 第二次“正式解析”：解析所有参数
    # -----------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description="Export a small sample CSV or export one template row by primary key."
    )

    # 运行配置文件路径
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )

    # 目标表名
    # 默认取环境变量 TARGET_TABLE
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))

    # 表配置文件路径
    # 默认取环境变量 TABLE_PROFILE_PATH
    # 如果环境变量没配，就回退到 config/table_profiles.json
    parser.add_argument(
        "--profile-file",
        default=os.getenv("TABLE_PROFILE_PATH", "config/table_profiles.json"),
        help="Path to the table profile JSON file.",
    )

    # 样本导出条数
    # 只有在没有 --pk-value 时，这个参数才有意义
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("EXPORT_SAMPLE_LIMIT", "3")),
        help="How many rows to export when --pk-value is not provided.",
    )

    # 如果用户知道某条记录的主键值，
    # 就可以通过这个参数精确导出这 1 条模板
    parser.add_argument(
        "--pk-value",
        help="Primary key value of the exact record to export as template.",
    )

    # 如果用户明确知道主键列名，也可以手工指定
    # 否则脚本会自己按优先级去找：
    # profile -> env -> 数据库扫描 -> 第一列兜底
    parser.add_argument(
        "--pk-column",
        help="Primary key column name. If omitted, the script will try profile -> database -> first column fallback.",
    )

    # 自定义输出文件路径
    # 如果不传，则脚本会自动决定输出到 sample.csv 或 template.csv
    parser.add_argument("--output", help="Output CSV path.")

    # 返回完整解析结果
    return parser.parse_args()


def validate_table_name(table_name: str) -> str:
    """
    校验表名是否合法。

    这里的目的主要是：
    - 防止空表名
    - 防止把危险字符带进 SQL 里的表名位置
    """

    # 如果表名为空，或者不符合正则，就直接报错
    if not table_name or not TABLE_NAME_RE.match(table_name):
        raise ValueError(
            "A single table name is required and may only contain letters, numbers, and underscores."
        )

    # 校验通过，原样返回
    return table_name


def get_profile_primary_key_columns(profile: dict | None) -> list[str]:
    """
    从表配置 profile 中读取主键列列表。

    profile 示例：
    {
        "primary_key_columns": ["id"]
    }

    如果 profile 不存在，或字段格式不对，返回空列表。
    """

    if not profile:
        return []

    value = profile.get("primary_key_columns", [])

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return []


def get_profile_json_columns(profile: dict | None) -> list[str]:
    """
    从表配置 profile 中读取 JSON 列列表。

    profile 示例：
    {
        "json_columns": ["profile", "extra"]
    }

    如果 profile 不存在，或字段格式不对，返回空列表。
    """

    if not profile:
        return []

    value = profile.get("json_columns", [])

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return []

    
def get_profile_column_order(profile: dict | None) -> list[str]:
    """
    从表配置 profile 中读取列顺序。

    设计目的：
    - 导出的 CSV 列顺序尽量稳定
    - 尽量与数据库实际列顺序或预先扫描到的列顺序保持一致

    如果 profile 不存在，或字段格式不对，返回空列表。
    """

    if not profile:
        return []

    value = profile.get("column_order", [])

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return []


def resolve_primary_key_column(
    args: argparse.Namespace,
    db,
    table_name: str,
    profile: dict | None,
) -> tuple[str, str]:
    """
    按最直白的优先级确定主键列。

    返回值：
    - 第一个值：主键列名
    - 第二个值：主键来源说明，用于日志输出

    优先级：
    1. 命令行显式指定
    2. 表配置文件
    3. 环境变量 PRIMARY_KEY_COLUMNS
    4. 数据库扫描主键
    5. 数据库第一列兜底
    """

    # 1. 如果命令行显式传了 --pk-column，优先使用
    if args.pk_column:
        return args.pk_column.strip(), "command_line"

    # 2. 如果表配置文件里有主键定义，优先使用配置
    profile_pk_columns = get_profile_primary_key_columns(profile)
    if profile_pk_columns:
        return profile_pk_columns[0], "table_profile"

    # 3. 如果环境变量 PRIMARY_KEY_COLUMNS 有配置，也可以作为来源
    env_pk_columns = parse_column_list(os.getenv("PRIMARY_KEY_COLUMNS"))
    if env_pk_columns:
        return env_pk_columns[0], "env"

    # 4. 如果前面都没有，就调用数据库扫描方法
    # 让数据库自己告诉我们主键列
    db_pk_columns = db.get_primary_key_columns(table_name)
    if db_pk_columns:
        return db_pk_columns[0], "database_scan"

    # 5. 如果数据库元信息也没给出主键，就退回最简单的兜底方案：
    # 把第一列当成主键
    first_column = db.get_first_column_name(table_name)
    if first_column:
        return first_column, "first_column_fallback"

    # 如果连第一列都拿不到，说明表结构异常或访问失败，直接报错
    raise ValueError("Could not determine the primary key column for this table.")


def normalize_json_for_csv(value: object) -> str:
    """
    把数据库里的 JSON 值整理成 CSV 可安全保存的 JSON 字符串。

    这里不做任何业务改造，只做两件事：
    1. 空值写成空字符串
    2. 非空 JSON 统一压缩成合法 JSON 字符串

    说明：
    - 这里的目标是“标准化保存”，不是“修改 JSON 内容”
    - CSV 里最终存的是 JSON 字符串
    """

    # 数据库里是 NULL 时，CSV 中写空字符串
    if value is None:
        return ""

    # 先统一转成字符串并去掉两端空白
    raw_text = str(value).strip()

    # 如果是空字符串，也写成空字符串
    if raw_text == "":
        return ""

    # 先 loads 再 dumps，有两个目的：
    # 1. 校验这是不是合法 JSON
    # 2. 统一输出成紧凑规范的 JSON 字符串
    parsed = json.loads(raw_text)

    # ensure_ascii=False：
    # 中文不转 \uXXXX，便于人工查看
    # separators=(",", ":")：
    # 压缩掉多余空格，让 JSON 更紧凑
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def resolve_json_columns(profile: dict | None, db, table_name: str) -> list[str]:
    """
    解析当前表的 JSON 列。

    来源做并集：
    1. 环境变量 JSON_COLUMNS
    2. 表配置文件中的 json_columns
    3. 数据库扫描得到的 JSON 列

    这么做的目的是：
    - 配置可以显式补充
    - 数据库扫描可以自动发现
    - 最终尽量不漏掉 JSON 列
    """

    # 从环境变量读取 JSON_COLUMNS
    configured_columns = parse_column_list(os.getenv("JSON_COLUMNS"))

    # 从表配置文件读取 json_columns
    profile_columns = get_profile_json_columns(profile)

    # 从数据库扫描 JSON 列
    database_columns = db.get_json_columns(table_name)

    # 取并集，去重后排序，保证输出稳定
    return sorted(set(configured_columns) | set(profile_columns) | set(database_columns))


def normalize_rows(
    rows: list[dict],
    json_columns: list[str],
    column_order: list[str],
) -> tuple[list[str], list[dict]]:
    """
    把数据库查询结果规范化成适合写 CSV 的结构。

    输入：
    - rows：数据库查询得到的多行 dict
    - json_columns：哪些列要按 JSON 处理
    - column_order：导出 CSV 时希望使用的列顺序

    输出：
    - fieldnames：CSV 表头顺序
    - normalized_rows：每一行都已经规范化成可写入 CSV 的字典
    """

    # 如果数据库没查到任何行，直接返回空结果
    if not rows:
        return [], []

    # 优先使用指定的列顺序。
    # 如果没有列顺序配置，就按第一行 dict 的键顺序来决定输出顺序。
    fieldnames = column_order[:] if column_order else list(rows[0].keys())

    # 这里存放所有规范化后的结果行
    normalized_rows: list[dict] = []

    # 逐行处理原始数据库记录
    for raw_row in rows:
        # 这一行对应的规范化结果
        normalized_row: dict[str, object] = {}

        # 按 fieldnames 指定的顺序逐列处理
        for column in fieldnames:
            # 用 get() 是为了避免某些列在当前行字典里不存在时直接报 KeyError
            value = raw_row.get(column)

            # 如果当前列是 JSON 列，就走 JSON 规范化逻辑
            if column in json_columns:
                normalized_row[column] = normalize_json_for_csv(value)

            # 如果值是 None，CSV 里写空字符串
            elif value is None:
                normalized_row[column] = ""

            # 其他情况统一转成字符串
            # 因为 CSV 本身就是文本中间态
            else:
                normalized_row[column] = str(value)

        # 一行处理完成后，加入结果列表
        normalized_rows.append(normalized_row)

    # 返回 CSV 表头和数据行
    return fieldnames, normalized_rows


def write_csv(output_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    """
    把规范化后的数据写成 CSV 文件。

    设计考虑：
    - 自动创建父目录
    - 使用 utf-8-sig，兼容 Excel 打开
    - newline="" 避免 Windows 下写出空行
    """

    # 如果父目录不存在，就自动创建
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 以写模式打开文件
    # utf-8-sig：兼容 Excel
    # newline=""：csv 官方推荐写法，避免额外空行
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        # 创建 DictWriter，按 fieldnames 指定的顺序写列
        writer = csv.DictWriter(handle, fieldnames=fieldnames)

        # 先写表头
        writer.writeheader()

        # 再写所有数据行
        writer.writerows(rows)


def main() -> int:
    """
    脚本主入口。

    这里是整个导出流程的编排层：
    1. 解析参数
    2. 校验表名
    3. 连接数据库
    4. 读取表配置
    5. 确定 JSON 列和列顺序
    6. 根据是否传入 pk-value，分两条路径：
       - 按主键导出单条模板
       - 按 limit 导出样本
    7. 规范化并写出 CSV
    8. 无论成功失败都断开数据库连接
    """

    # 先解析命令行参数
    args = parse_args()

    # 延迟导入项目内模块。
    # 这样做的好处是：
    # - 用户只看 --help 时，不会过早触发数据库层依赖
    # - 脚本启动体验更清楚
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

    # limit 必须大于 0
    if args.limit <= 0:
        print("[ERROR] --limit must be greater than 0.")
        return 1

    # -------------------------------------------------------------
    # 第二步：确定输出路径
    # -------------------------------------------------------------
    # CSV_BASE_DIR 默认是 data
    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))

    # 如果用户传了 --pk-value，说明是“模板模式”，默认文件名是 template.csv
    # 否则是“样本模式”，默认文件名是 sample.csv
    default_file_name = "template.csv" if args.pk_value is not None else "sample.csv"

    # 如果用户手工传了 --output，则优先使用用户指定路径
    # 否则就按默认规则输出到 data/<table>/sample.csv 或 template.csv
    output_path = Path(args.output) if args.output else csv_base_dir / table_name / default_file_name

    # -------------------------------------------------------------
    # 第三步：建立数据库连接
    # -------------------------------------------------------------
    db = DatabaseManager()

    # connect() 返回 False 表示连接失败
    if not db.connect():
        print("[ERROR] Database connection failed.")
        return 1

    try:
        # ---------------------------------------------------------
        # 第四步：读取表配置和数据库元信息
        # ---------------------------------------------------------
        # 从 profile 文件中取当前表的配置
        profile = get_table_profile(args.profile_file, table_name)

        # 解析 JSON 列
        json_columns = resolve_json_columns(profile, db, table_name)

        # 确定导出时使用的列顺序
        # 优先用 profile 中的 column_order
        # 如果没有，则从数据库取实际列名顺序
        column_order = get_profile_column_order(profile) or db.get_column_names(table_name)

        # ---------------------------------------------------------
        # 第五步：如果指定了 pk-value，则走“单条模板导出”路径
        # ---------------------------------------------------------
        if args.pk_value is not None:
            # 确定主键列名，以及主键来源
            pk_column, pk_source = resolve_primary_key_column(args, db, table_name, profile)

            # 只查符合主键值的记录。
            # LIMIT 2 的用意：
            # - 正常情况下应只匹配 1 条
            # - 如果匹配到 2 条，说明主键列选择可能有问题，或者数据不符合预期
            sql = f"SELECT * FROM `{table_name}` WHERE `{pk_column}` = %s LIMIT 2"

            # 参数化传值，避免把 pk_value 直接拼进 SQL
            rows = db.query_dicts(sql, (args.pk_value,))

            # 如果一条都没查到，直接报错
            if len(rows) == 0:
                print(f"[ERROR] No record found in {table_name} where {pk_column} = {args.pk_value}.")
                return 1

            # 如果查到多条，也报错
            # 这表示“主键列不唯一”或“你指定的主键列不对”
            if len(rows) > 1:
                print(
                    "[ERROR] More than one row matched the requested primary key value. "
                    "Please check the table data or specify the correct primary key column."
                )
                return 1

            # 把查询到的 1 条记录规范化成可写 CSV 的格式
            fieldnames, normalized_rows = normalize_rows(rows, json_columns, column_order)

            # 写出 template.csv
            write_csv(output_path, fieldnames, normalized_rows)

            # 输出成功信息，方便用户确认
            print(f"[OK] Exported exactly one template row from {table_name}.")
            print(f"Output: {output_path}")
            print(f"Primary key column: {pk_column} ({pk_source})")
            print(f"Primary key value: {args.pk_value}")
            print(f"JSON columns: {json_columns if json_columns else '(none)'}")
            print("Next step: confirm template.csv and use expand_rows.py to generate chunk files.")
            return 0

        # ---------------------------------------------------------
        # 第六步：如果没有 pk-value，则走“样本导出”路径
        # ---------------------------------------------------------
        # 这里的目标是“取前 N 条作为样本”
        sql = f"SELECT * FROM `{table_name}` LIMIT {args.limit}"

        # 查询结果以“list[dict]”形式返回
        rows = db.query_dicts(sql)

        # 规范化处理
        fieldnames, normalized_rows = normalize_rows(rows, json_columns, column_order)

        # 写出 sample.csv
        write_csv(output_path, fieldnames, normalized_rows)

        # 输出成功信息
        print(f"[OK] Exported {len(normalized_rows)} sample rows from {table_name}.")
        print(f"Output: {output_path}")
        print(f"JSON columns: {json_columns if json_columns else '(none)'}")
        print("Next step: choose one good row, keep it in template.csv, then run expand_rows.py.")
        return 0

    except Exception as exc:
        # 这里统一兜底所有异常，避免用户只看到 Python traceback
        # 而是先给一个明确的业务错误提示
        print(f"[ERROR] Export failed: {exc}")
        return 1

    finally:
        # 无论成功还是失败，都要主动断开数据库连接
        # 这样更适合短连接场景，也更容易做安全评审解释
        db.disconnect()


# Python 脚本标准入口。
# 只有当这个文件被直接运行时，才会执行 main()。
if __name__ == "__main__":
    sys.exit(main())