"""
Pre-execution checks: PK conflict detection.

Runs before actual insertion to detect existing records in the planned PK range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.db.connection import DatabaseManager
from src.config.app_config import ConnectionConfig
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan, TaskItem
from src.strategy.pk_planner import (
    analyze_pk_pattern, format_pk_value, check_pk_conflict,
)


@dataclass
class ConflictInfo:
    """Conflict result for one table."""
    table_name: str
    pk_column: str
    planned_start: str = ""
    planned_end: str = ""
    conflict_count: int = 0
    conflict_samples: list[str] = field(default_factory=list)


@dataclass
class PreflightResult:
    """Result of the preflight PK conflict check."""
    conflicts: list[ConflictInfo] = field(default_factory=list)
    checked_tables: int = 0
    error: str = ""

    @property
    def has_conflicts(self) -> bool:
        return any(c.conflict_count > 0 for c in self.conflicts)


def _compute_pk_range(task: TaskItem, current_max: Any, sample_pk: Any) -> tuple[list[str], str, str]:
    """
    Compute the list of planned PK values for a task.
    Returns (values, first_value, last_value).
    """
    pattern = analyze_pk_pattern(sample_pk)
    pk_cfg = task.pk_config

    # Override pattern with explicit config
    if pk_cfg.prefix:
        pattern["prefix"] = pk_cfg.prefix
    if pk_cfg.zero_pad_width > 0:
        pattern["zero_pad_width"] = pk_cfg.zero_pad_width

    # Determine start
    if pk_cfg.mode == "fixed_start" and pk_cfg.start_value is not None:
        start = pk_cfg.start_value
    elif pk_cfg.mode == "explicit_range" and pk_cfg.start_value is not None:
        start = pk_cfg.start_value
    elif pk_cfg.mode == "auto_increment_from_max":
        if current_max is not None:
            max_p = analyze_pk_pattern(current_max)
            start = (max_p["numeric_part"] + 1) if max_p["numeric_part"] is not None else 1
        elif pattern["numeric_part"] is not None:
            start = pattern["numeric_part"] + 1
        else:
            start = 1
    else:
        start = pk_cfg.start_value or 1

    # Determine total
    if pk_cfg.mode == "explicit_range" and pk_cfg.end_value is not None:
        total = pk_cfg.end_value - start + 1
    else:
        total = task.row_count

    if total <= 0:
        return [], "", ""

    first_val = format_pk_value(start, pattern)
    last_val = format_pk_value(start + total - 1, pattern)

    # For conflict checking, we only need to generate the full list for
    # reasonable counts. For very large ranges, use SQL BETWEEN instead.
    values = []
    for i in range(total):
        values.append(format_pk_value(start + i, pattern))

    return values, first_val, last_val


def _check_range_conflict(db: DatabaseManager, table_name: str, pk_column: str,
                          first_val: str, last_val: str, total: int) -> ConflictInfo:
    """
    Check conflicts using BETWEEN for large ranges, IN for small ones.
    """
    info = ConflictInfo(
        table_name=table_name,
        pk_column=pk_column,
        planned_start=first_val,
        planned_end=last_val,
    )

    try:
        # Use COUNT + BETWEEN for efficiency
        sql_count = (
            f"SELECT COUNT(*) FROM `{table_name}` "
            f"WHERE `{pk_column}` BETWEEN %s AND %s"
        )
        rows = db.query(sql_count, (first_val, last_val))
        count = int(rows[0][0]) if rows else 0
        info.conflict_count = count

        if count > 0:
            # Get sample conflicting values
            sql_sample = (
                f"SELECT `{pk_column}` FROM `{table_name}` "
                f"WHERE `{pk_column}` BETWEEN %s AND %s "
                f"ORDER BY `{pk_column}` LIMIT 10"
            )
            sample_rows = db.query(sql_sample, (first_val, last_val))
            info.conflict_samples = [str(r[0]) for r in sample_rows]

    except Exception as exc:
        logger.warning(f"Conflict check failed for {table_name}.{pk_column}: {exc}")
        info.conflict_count = -1
        info.conflict_samples = [f"(check error: {exc})"]

    return info


def run_preflight_check(
    plan: CampaignPlan,
    conn_config: ConnectionConfig,
    scan_result: DatabaseScanResult | None = None,
    db: DatabaseManager | None = None,
) -> PreflightResult:
    """
    Check PK conflicts for all tasks in the campaign plan.

    Args:
        plan: Campaign plan with tasks
        conn_config: Database connection config
        scan_result: Cached scan result for metadata
        db: Optional shared DatabaseManager (persistent session)

    Returns:
        PreflightResult with conflict details per table
    """
    result = PreflightResult()

    shared = db is not None
    if not shared:
        db = DatabaseManager(config=conn_config)
        if not db.connect():
            result.error = "Cannot connect to database for preflight check"
            return result

    try:
        for task in plan.tasks:
            if task.mode == "export":
                # Export mode doesn't insert, skip conflict check
                continue

            table_name = task.table_name
            meta = scan_result.tables.get(table_name) if scan_result else None
            pk_cols = meta.primary_key_columns if meta else db.get_primary_key_columns(table_name)
            if not pk_cols:
                continue

            pk_col = pk_cols[0]

            # Get current max and sample PK for pattern detection
            current_max = db.get_max_pk_value(table_name, pk_col)
            sample_pk = current_max  # Use max as sample for pattern analysis
            if sample_pk is None:
                # Table is empty, no possible conflicts
                result.checked_tables += 1
                continue

            planned_values, first_val, last_val = _compute_pk_range(
                task, current_max, sample_pk
            )

            if not first_val or not last_val:
                result.checked_tables += 1
                continue

            info = _check_range_conflict(db, table_name, pk_col, first_val, last_val, task.row_count)
            result.conflicts.append(info)
            result.checked_tables += 1

            if info.conflict_count > 0:
                logger.warning(
                    f"PK conflict: {table_name}.{pk_col} "
                    f"range [{first_val}~{last_val}] has {info.conflict_count} existing rows"
                )

    finally:
        if not shared:
            db.disconnect()

    return result
