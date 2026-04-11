#!/usr/bin/env python3
"""
full_mock_db_test.py — MySQL Data Factory 3.00 本地全库压力验证

目标：
  Phase 1  连接 cloverit_mock 并确认表结构
  Phase 2  扫描所有表，分析 PK / UK / 列类型，分 A/B/C 三类
  Phase 3  为尽可能多的表注入 3 条种子数据
  Phase 4  对已有种子数据的表运行批量扩张（目标每表 50,000 条）
  Phase 5  输出结构化 Markdown 测试报告

运行方式：
  python scripts/full_mock_db_test.py --env-file .env.mock [--skip-seed] [--skip-expand]
  python scripts/full_mock_db_test.py --env-file .env.mock --expand-rows 5000
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────

# 种子数据：每张表插入这么多行
SEED_ROWS = 3

# 批量扩张默认目标（可被 --expand-rows 覆盖）
DEFAULT_EXPAND_ROWS = 50_000

# Spring Batch / Liquibase 系统表，完全跳过
SYSTEM_TABLES = {
    "batch_job_execution",
    "batch_job_execution_context",
    "batch_job_execution_params",
    "batch_job_execution_params_old",
    "batch_job_execution_seq",
    "batch_job_instance",
    "batch_job_seq",
    "batch_step_execution",
    "batch_step_execution_context",
    "batch_step_execution_seq",
    "databasechangelog",
    "databasechangeloglock",
}


# ─────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────

@dataclass
class ColumnInfo:
    name: str
    col_type: str        # e.g. "bigint", "varchar(10)", "datetime"
    is_nullable: bool
    default: str | None
    extra: str           # "auto_increment" etc.
    col_key: str         # PRI / UNI / MUL / ""
    max_len: int | None  # parsed from varchar(N)


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    pk_cols: list[str]
    uk_groups: list[list[str]]   # each group is one UNIQUE KEY
    has_autoincrement_pk: bool
    category: str = "A"          # A / B / C
    category_reason: str = ""

    @property
    def non_pk_required_cols(self) -> list[ColumnInfo]:
        pk_set = set(self.pk_cols)
        return [c for c in self.columns if not c.is_nullable and c.default is None
                and c.extra != "auto_increment" and c.name not in pk_set]


@dataclass
class SeedResult:
    table: str
    success: bool
    rows_inserted: int = 0
    error: str = ""


@dataclass
class ExpandResult:
    table: str
    success: bool
    rows_inserted: int = 0
    duration_sec: float = 0.0
    error: str = ""


# ─────────────────────────────────────────────
# 列元数据解析
# ─────────────────────────────────────────────

def parse_max_len(col_type: str) -> int | None:
    """从 varchar(N) / char(N) 提取 N"""
    import re
    m = re.match(r"(?:var)?char\((\d+)\)", col_type, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def parse_base_type(col_type: str) -> str:
    """bigint unsigned → bigint; varchar(10) → varchar"""
    import re
    t = re.split(r"[\s(]", col_type)[0].lower()
    return t


def fetch_table_infos(db_conn) -> dict[str, TableInfo]:
    """从 information_schema 读取所有表的列、PK、UK 信息"""
    schema = db_conn.database

    # 列信息
    col_sql = f"""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
               COLUMN_DEFAULT, EXTRA, COLUMN_KEY
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    # UK 约束
    uk_sql = f"""
        SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = '{schema}'
          AND NON_UNIQUE = 0
          AND INDEX_NAME != 'PRIMARY'
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
    """

    col_rows = db_conn.query_dicts(col_sql)
    uk_rows = db_conn.query_dicts(uk_sql)

    # ── 构建 UK 分组 ──────────────────────────────
    from collections import defaultdict
    # table → index_name → [col, ...]
    uk_map: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in (uk_rows or []):
        tbl = r["TABLE_NAME"]
        idx = r["INDEX_NAME"]
        col = r["COLUMN_NAME"]
        uk_map[tbl][idx].append(col)

    # ── 构建 TableInfo ────────────────────────────
    tables: dict[str, TableInfo] = {}
    cur_table = None
    cur_cols: list[ColumnInfo] = []
    cur_pks: list[str] = []
    has_ai = False

    def flush():
        nonlocal cur_table, cur_cols, cur_pks, has_ai
        if cur_table:
            uk_groups = list(uk_map.get(cur_table, {}).values())
            tables[cur_table] = TableInfo(
                name=cur_table,
                columns=list(cur_cols),
                pk_cols=list(cur_pks),
                uk_groups=uk_groups,
                has_autoincrement_pk=has_ai,
            )
        cur_cols = []
        cur_pks = []
        has_ai = False

    for r in (col_rows or []):
        tname = r["TABLE_NAME"]
        if tname != cur_table:
            flush()
            cur_table = tname
        ci = ColumnInfo(
            name=r["COLUMN_NAME"],
            col_type=r["COLUMN_TYPE"],
            is_nullable=(r["IS_NULLABLE"] == "YES"),
            default=r["COLUMN_DEFAULT"],
            extra=r["EXTRA"] or "",
            col_key=r["COLUMN_KEY"] or "",
            max_len=parse_max_len(r["COLUMN_TYPE"]),
        )
        cur_cols.append(ci)
        if r["COLUMN_KEY"] == "PRI":
            cur_pks.append(r["COLUMN_NAME"])
        if "auto_increment" in (r["EXTRA"] or "").lower():
            has_ai = True

    flush()
    return tables


# ─────────────────────────────────────────────
# 表分类逻辑
# ─────────────────────────────────────────────

def classify_table(info: TableInfo) -> tuple[str, str]:
    """返回 (category, reason)"""
    if info.name in SYSTEM_TABLES:
        return "C", "Spring Batch / Liquibase 系统表，有外键依赖，跳过"

    # 无主键
    if not info.pk_cols:
        return "C", "无主键列，无法安全扩张"

    # 复合主键且不含 auto_increment → 需要生成组合值，B 类
    if len(info.pk_cols) > 1 and not info.has_autoincrement_pk:
        return "B", f"复合主键 ({','.join(info.pk_cols)})，需要特别生成组合值"

    # 评估必填非 PK 列数量
    required = info.non_pk_required_cols
    if len(required) > 5:
        return "B", f"有 {len(required)} 个 NOT NULL 非 PK 列，需要精心生成"

    return "A", "结构简单，可直接自动生成种子 + 扩张"


# ─────────────────────────────────────────────
# 种子值生成
# ─────────────────────────────────────────────

BASE_DATETIME = "2024-01-01 00:00:00"
BASE_DATE = "2024-01-01"
BASE_INT = 1000


def generate_seed_value(col: ColumnInfo, row_idx: int, table_name: str) -> str | None:
    """为单列生成种子值。返回 None 表示让 DB 处理（nullable/default）。"""
    base = parse_base_type(col.col_type)
    n = row_idx + 1  # 1-based

    # ── 整数类 ──────────────────────────────────
    if base in ("bigint", "int", "tinyint", "smallint", "mediumint"):
        if col.col_key == "PRI" and not col.has_ai_hint():
            return str(BASE_INT + n)
        if col.col_key == "PRI":
            return None  # auto_increment
        return str(n)

    # ── 字符串类 ─────────────────────────────────
    if base in ("varchar", "char"):
        if col.max_len is None:
            return f"T{n:03d}"
        if col.max_len == 1:
            return "0"
        if col.max_len == 2:
            return "00"
        if col.max_len <= 6:
            raw = f"T{n:03d}"
            return raw[:col.max_len]
        if col.max_len <= 10:
            raw = f"TEST{n:04d}"
            return raw[:col.max_len]
        raw = f"SEED_{table_name[:8]}_{n:04d}"
        return raw[:col.max_len]

    # ── 日期时间 ─────────────────────────────────
    if base == "datetime":
        return BASE_DATETIME
    if base == "date":
        return BASE_DATE
    if base == "timestamp":
        return BASE_DATETIME

    # ── 数值 ─────────────────────────────────────
    if base in ("decimal", "numeric", "float", "double"):
        return "0"

    # ── 文本 ─────────────────────────────────────
    if base in ("text", "mediumtext", "longtext", "tinytext"):
        return "seed"

    # ── JSON ─────────────────────────────────────
    if base == "json":
        return "{}"

    # ── 二进制 ───────────────────────────────────
    if base in ("blob", "mediumblob", "longblob"):
        return None  # skip

    return f"V{n}"


# monkey-patch has_ai_hint
def _has_ai_hint(self: ColumnInfo) -> bool:
    return "auto_increment" in self.extra.lower()
ColumnInfo.has_ai_hint = _has_ai_hint  # type: ignore


def build_insert_sql(info: TableInfo, row_idx: int) -> str | None:
    """构建单行 INSERT SQL"""
    cols_to_set: list[tuple[str, str]] = []

    pk_set = set(info.pk_cols)

    for col in info.columns:
        # AUTO_INCREMENT PK：跳过
        if col.has_ai_hint():
            continue

        val = generate_seed_value(col, row_idx, info.name)

        # PK 列必须有值
        if col.name in pk_set:
            if val is None:
                val = str(BASE_INT + row_idx + 1)
            cols_to_set.append((col.name, val))
            continue

        # 非 PK：若 nullable 或有 default，跳过（让 DB 填）
        if col.is_nullable or col.default is not None:
            # 但如果是 NOT NULL 无 default，必须填
            pass
        elif val is None:
            val = "0"

        if val is not None:
            cols_to_set.append((col.name, val))

    if not cols_to_set:
        return None

    col_part = ", ".join(f"`{c}`" for c, _ in cols_to_set)
    val_part = ", ".join(f"'{v.replace(chr(39), chr(39)+chr(39))}'" for _, v in cols_to_set)
    return f"INSERT INTO `{info.name}` ({col_part}) VALUES ({val_part});"


# ─────────────────────────────────────────────
# Phase 3：种子注入
# ─────────────────────────────────────────────

def run_seed_phase(
    db_conn,
    table_infos: dict[str, TableInfo],
    n_rows: int = SEED_ROWS,
) -> list[SeedResult]:
    results: list[SeedResult] = []

    # 先插 A 类，再插 B 类
    ordered = (
        [t for t in table_infos.values() if t.category == "A"] +
        [t for t in table_infos.values() if t.category == "B"]
    )

    for info in ordered:
        inserted = 0
        last_err = ""
        for i in range(n_rows):
            sql = build_insert_sql(info, i)
            if sql is None:
                last_err = "无法构建 INSERT"
                break
            try:
                db_conn.execute(sql)
                inserted += 1
            except Exception as e:
                last_err = str(e)
                # 如果是重复键，尝试继续下一行
                if "duplicate" in last_err.lower() or "1062" in last_err:
                    continue
                break

        success = inserted > 0
        results.append(SeedResult(
            table=info.name,
            success=success,
            rows_inserted=inserted,
            error=last_err if not success else ("" if inserted == n_rows else f"部分插入: {last_err}"),
        ))
        status = "OK" if success else "FAIL"
        print(f"  [{status}] {info.name}: {inserted}/{n_rows} rows"
              + (f"  -- {last_err[:80]}" if last_err and not success else ""))

    return results


# ─────────────────────────────────────────────
# Phase 4：批量扩张
# ─────────────────────────────────────────────

def run_expand_phase(
    conn_config,
    paths,
    scan_result,
    table_infos: dict[str, TableInfo],
    seed_results: list[SeedResult],
    target_rows: int,
    db_conn=None,
) -> list[ExpandResult]:
    from src.plan.models import CampaignPlan, TaskItem
    from src.workflow.campaign_runner import run_campaign

    # 只对成功注入种子的表做扩张
    seeded = {r.table for r in seed_results if r.success}

    # 从 scan_result 中只保留 seeded 的表
    eligible = [
        t for t in table_infos.values()
        if t.name in seeded and t.category in ("A", "B")
    ]

    if not eligible:
        print("  [WARN] 没有合适的表可以扩张")
        return []

    print(f"  准备对 {len(eligible)} 张表执行扩张，目标每表 {target_rows:,} 行")

    results: list[ExpandResult] = []

    for info in eligible:
        table_name = info.name
        t0 = time.perf_counter()
        print(f"\n  → {table_name} ...")

        try:
            # 获取 scan_result 里的表元数据
            table_meta = scan_result.tables.get(table_name)
            if table_meta is None:
                results.append(ExpandResult(table=table_name, success=False,
                                             error="scan_result 中无元数据"))
                continue

            if table_meta.row_count == 0:
                # 刷新行数
                table_meta.row_count = _count_rows(db_conn, table_name)

            if table_meta.row_count == 0:
                results.append(ExpandResult(table=table_name, success=False,
                                             error="种子数据行数为 0，无法生成模板"))
                continue

            # 构建单任务 CampaignPlan
            # batch_size 同时控制 chunk 大小和 INSERT 批次大小
            task = TaskItem(
                table_name=table_name,
                row_count=target_rows,
                batch_size=5000,
                mode="insert",
                sample_method="first_row",
            )
            plan = CampaignPlan(tasks=[task])

            run_result = run_campaign(
                plan=plan,
                conn_config=conn_config,
                paths=paths,
                scan_result=scan_result,
                db=db_conn,
            )

            elapsed = time.perf_counter() - t0
            report = run_result.reports[0] if run_result.reports else None
            if report and report.status == "completed":
                rows_done = report.total_rows_inserted
                results.append(ExpandResult(
                    table=table_name,
                    success=True,
                    rows_inserted=rows_done,
                    duration_sec=elapsed,
                ))
                print(f"     OK  {rows_done:,} rows in {elapsed:.1f}s")
            else:
                err = report.error_summary if report else "unknown"
                results.append(ExpandResult(
                    table=table_name,
                    success=False,
                    duration_sec=elapsed,
                    error=err,
                ))
                print(f"     FAIL  {err[:100]}")

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            results.append(ExpandResult(
                table=table_name,
                success=False,
                duration_sec=elapsed,
                error=str(exc),
            ))
            print(f"     ERROR  {str(exc)[:100]}")

    return results


def _count_rows(db_conn, table_name: str) -> int:
    try:
        rows = db_conn.query_dicts(f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
        return int(rows[0]["cnt"]) if rows else 0
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Phase 5：输出报告
# ─────────────────────────────────────────────

def generate_report(
    table_infos: dict[str, TableInfo],
    seed_results: list[SeedResult],
    expand_results: list[ExpandResult],
    conn_config,
    target_rows: int,
    total_tables: int,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    a = lambda s: lines.append(s)

    a(f"# MySQL Data Factory — 本地全库压力验证报告")
    a(f"")
    a(f"生成时间：{now}")
    a(f"")

    # ── A. 环境确认 ──────────────────────────────
    a(f"## A. 环境确认")
    a(f"")
    a(f"| 项目 | 值 |")
    a(f"|------|----|")
    a(f"| 容器 | cloverit-fullmock-db |")
    a(f"| 端口 | {conn_config.port} |")
    a(f"| 数据库 | {conn_config.database} |")
    a(f"| 总表数 | {total_tables} |")
    a(f"| 系统表（跳过）| {len(SYSTEM_TABLES)} |")
    a(f"| 业务表 | {total_tables - len(SYSTEM_TABLES)} |")
    a(f"")

    # 表分类统计
    cat_a = [t for t in table_infos.values() if t.category == "A"]
    cat_b = [t for t in table_infos.values() if t.category == "B"]
    cat_c = [t for t in table_infos.values() if t.category == "C"]

    a(f"### 表分类")
    a(f"")
    a(f"| 分类 | 数量 | 说明 |")
    a(f"|------|------|------|")
    a(f"| A 类（直接自动） | {len(cat_a)} | 结构简单，自动种子 + 扩张 |")
    a(f"| B 类（需要关注）| {len(cat_b)} | 复合主键或较多必填列 |")
    a(f"| C 类（跳过）    | {len(cat_c)} | 系统表或无主键 |")
    a(f"")

    # ── B. 种子数据 ──────────────────────────────
    a(f"## B. 种子数据注入结果")
    a(f"")
    seed_ok = [r for r in seed_results if r.success]
    seed_fail = [r for r in seed_results if not r.success]
    a(f"- 成功插入: **{len(seed_ok)}** 张表")
    a(f"- 失败: **{len(seed_fail)}** 张表")
    a(f"")

    if seed_ok:
        a(f"### 成功表")
        a(f"")
        a(f"| 表名 | 插入行数 | 备注 |")
        a(f"|------|---------|------|")
        for r in seed_ok:
            note = r.error if r.error else "OK"
            a(f"| {r.table} | {r.rows_inserted} | {note} |")
        a(f"")

    if seed_fail:
        a(f"### 失败表")
        a(f"")
        a(f"| 表名 | 失败原因 |")
        a(f"|------|---------|")
        for r in seed_fail:
            a(f"| {r.table} | {r.error[:120]} |")
        a(f"")

    # ── C. 扩张测试 ──────────────────────────────
    a(f"## C. 批量扩张测试结果")
    a(f"")
    a(f"目标: 每表 {target_rows:,} 行")
    a(f"")
    exp_ok = [r for r in expand_results if r.success]
    exp_fail = [r for r in expand_results if not r.success]
    a(f"- 成功扩张: **{len(exp_ok)}** 张表")
    a(f"- 失败: **{len(exp_fail)}** 张表")
    a(f"")

    if exp_ok:
        total_inserted = sum(r.rows_inserted for r in exp_ok)
        a(f"### 成功扩张表")
        a(f"")
        a(f"| 表名 | 插入行数 | 耗时(s) | 速率(行/s) |")
        a(f"|------|---------|---------|-----------|")
        for r in exp_ok:
            rate = int(r.rows_inserted / r.duration_sec) if r.duration_sec > 0 else 0
            a(f"| {r.table} | {r.rows_inserted:,} | {r.duration_sec:.1f} | {rate:,} |")
        a(f"")
        a(f"**总计插入: {total_inserted:,} 行**")
        a(f"")

    if exp_fail:
        a(f"### 失败表及原因")
        a(f"")
        a(f"| 表名 | 失败原因 |")
        a(f"|------|---------|")
        for r in exp_fail:
            a(f"| {r.table} | {r.error[:150]} |")
        a(f"")

    # ── D. 工具稳定性评价 ─────────────────────────
    a(f"## D. 工具稳定性评价")
    a(f"")
    success_rate = len(exp_ok) / max(len(expand_results), 1) * 100

    if success_rate >= 90:
        verdict = "**稳定，推荐明天上堡垒机**"
    elif success_rate >= 70:
        verdict = "**基本可用，建议先修复已知失败场景再上堡垒机**"
    else:
        verdict = "**稳定性有问题，建议先修复再上堡垒机**"

    a(f"- 扩张成功率: {success_rate:.1f}%")
    a(f"- 综合评价: {verdict}")
    a(f"")

    # 失败原因分类
    if exp_fail:
        err_cats = {}
        for r in exp_fail:
            err_lower = r.error.lower()
            if "duplicate" in err_lower or "1062" in err_lower:
                k = "主键/唯一键冲突"
            elif "foreign key" in err_lower or "1452" in err_lower:
                k = "外键约束失败"
            elif "data too long" in err_lower or "1406" in err_lower:
                k = "数据类型/长度问题"
            elif "sample" in err_lower or "template" in err_lower:
                k = "无法获取种子模板"
            else:
                k = "其他错误"
            err_cats[k] = err_cats.get(k, 0) + 1

        a(f"### 失败原因分类")
        a(f"")
        for cat, cnt in sorted(err_cats.items(), key=lambda x: -x[1]):
            a(f"- {cat}: {cnt} 张表")
        a(f"")

    # ── E. 明天上堡垒机建议 ──────────────────────
    a(f"## E. 明天上堡垒机建议")
    a(f"")
    a(f"### 建议先试的表")
    a(f"")
    a(f"优先选择本次成功扩张的表：")
    for r in exp_ok[:10]:
        rate = int(r.rows_inserted / r.duration_sec) if r.duration_sec > 0 else 0
        a(f"- `{r.table}` ({r.rows_inserted:,} rows, {rate:,} rows/s)")
    a(f"")

    a(f"### 建议初始规模")
    a(f"")
    a(f"- 第一轮：每表 **5,000 ~ 10,000** 行，验证工具与堡垒机网络连接稳定性")
    a(f"- 第二轮：成功后扩大到 **50,000 ~ 100,000** 行")
    a(f"- 避免第一次就全量，减少风险")
    a(f"")

    a(f"### 最需要注意的风险点")
    a(f"")
    a(f"1. **网络超时**：堡垒机环境网络延迟更高，建议调小 INSERT_BATCH_SIZE（推荐 200~300）")
    a(f"2. **主键冲突**：如果目标库已有数据，扩张前需要先 `SELECT MAX(pk)` 定位起点")
    a(f"3. **唯一键冲突**：本次本地测试发现的唯一键问题，堡垒机上同样会出现")
    a(f"4. **复合主键表（B 类）**：建议先人工确认模板数据质量再扩张")
    a(f"5. **连接稳定性**：优先使用 `--shared-connection` 模式（工具已支持）")
    a(f"")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="MySQL Data Factory 本地全库压力验证")
    parser.add_argument("--env-file", default=".env.mock")
    parser.add_argument("--skip-seed", action="store_true", help="跳过种子数据注入")
    parser.add_argument("--skip-expand", action="store_true", help="跳过批量扩张")
    parser.add_argument("--expand-rows", type=int, default=DEFAULT_EXPAND_ROWS,
                        help=f"每表扩张目标行数（默认 {DEFAULT_EXPAND_ROWS}）")
    parser.add_argument("--expand-tables", nargs="*", help="只扩张指定表（留空则全部）")
    parser.add_argument("--report-out", default="reports/full_mock_test_report.md",
                        help="报告输出路径")
    args = parser.parse_args()

    from src.config.app_config import load_dotenv_file, ConnectionConfig, AppPaths
    from src.db.connection import DatabaseManager
    from src.metadata.scanner import scan_database

    load_dotenv_file(args.env_file)
    conn = ConnectionConfig.from_env()
    paths = AppPaths()
    paths.ensure_all()

    print("=" * 60)
    print("MySQL Data Factory — 本地全库压力验证")
    print(f"目标: {conn.host}:{conn.port}/{conn.database}")
    print("=" * 60)

    # ── Phase 1: 连接确认 ──────────────────────
    print("\n[Phase 1] 连接确认 ...")
    db = DatabaseManager(config=conn)
    if not db.connect():
        print("[FAIL] 无法连接数据库")
        return 1

    tables_list = db.show_tables()
    print(f"  [OK] 已连接，发现 {len(tables_list)} 张表")

    # ── Phase 2: 扫描元数据 ─────────────────────
    print("\n[Phase 2] 扫描元数据 ...")
    scan_result = scan_database(db)
    print(f"  [OK] scan_database 完成，{len(scan_result.tables)} 张表")

    # 读取 information_schema 更完整的表信息
    print("  读取完整列/PK/UK 信息 ...")
    table_infos = fetch_table_infos(db)
    print(f"  [OK] fetch_table_infos 完成，{len(table_infos)} 张表")

    # 分类
    for info in table_infos.values():
        cat, reason = classify_table(info)
        info.category = cat
        info.category_reason = reason

    cat_counts = {"A": 0, "B": 0, "C": 0}
    for info in table_infos.values():
        cat_counts[info.category] += 1

    print(f"  分类: A={cat_counts['A']}  B={cat_counts['B']}  C={cat_counts['C']}")

    # 打印表清单
    print("\n  === 表分类清单 ===")
    for cat in ("A", "B", "C"):
        items = [t for t in table_infos.values() if t.category == cat]
        print(f"\n  [{cat}] {len(items)} 张")
        for t in items:
            pk_str = ",".join(t.pk_cols) if t.pk_cols else "(无主键)"
            uk_str = f"UK:{len(t.uk_groups)}" if t.uk_groups else ""
            ai_str = "[AUTO]" if t.has_autoincrement_pk else ""
            print(f"       {t.name:<40} PK:{pk_str:<20} {uk_str:<8} {ai_str}  -- {t.category_reason}")

    # ── Phase 3: 种子注入 ───────────────────────
    seed_results: list[SeedResult] = []

    if args.skip_seed:
        print("\n[Phase 3] 跳过种子注入（--skip-seed）")
        # 仍然统计哪些表有数据
        for info in table_infos.values():
            if info.category in ("A", "B"):
                cnt = _count_rows(db, info.name)
                if cnt > 0:
                    seed_results.append(SeedResult(table=info.name, success=True, rows_inserted=cnt))
    else:
        print(f"\n[Phase 3] 种子数据注入（每表 {SEED_ROWS} 行） ...")
        seed_results = run_seed_phase(db, table_infos, SEED_ROWS)
        ok_cnt = sum(1 for r in seed_results if r.success)
        print(f"\n  汇总: {ok_cnt}/{len(seed_results)} 张表成功注入种子数据")

    # ── Phase 4: 批量扩张 ───────────────────────
    expand_results: list[ExpandResult] = []

    if args.skip_expand:
        print("\n[Phase 4] 跳过批量扩张（--skip-expand）")
    else:
        # 筛选要扩张的表
        if args.expand_tables:
            filter_set = set(args.expand_tables)
        else:
            filter_set = None  # 全部

        filtered_infos = {
            k: v for k, v in table_infos.items()
            if filter_set is None or k in filter_set
        }
        filtered_seeds = [r for r in seed_results if filter_set is None or r.table in filter_set]

        print(f"\n[Phase 4] 批量扩张测试（目标每表 {args.expand_rows:,} 行） ...")
        expand_results = run_expand_phase(
            conn_config=conn,
            paths=paths,
            scan_result=scan_result,
            table_infos=filtered_infos,
            seed_results=filtered_seeds,
            target_rows=args.expand_rows,
            db_conn=db,
        )
        ok_cnt = sum(1 for r in expand_results if r.success)
        print(f"\n  汇总: {ok_cnt}/{len(expand_results)} 张表成功扩张")

    # ── Phase 5: 报告 ────────────────────────────
    print("\n[Phase 5] 生成报告 ...")
    report_md = generate_report(
        table_infos=table_infos,
        seed_results=seed_results,
        expand_results=expand_results,
        conn_config=conn,
        target_rows=args.expand_rows,
        total_tables=len(tables_list),
    )

    report_path = PROJECT_ROOT / args.report_out
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"  [OK] 报告已写入: {report_path}")

    # 同时打印到终端
    print("\n" + "=" * 60)
    print(report_md)

    db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())

