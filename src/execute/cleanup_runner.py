"""
Cleanup runner for test data removal.

Supports cleanup by:
- PK range
- run_id / campaign_id
- marker column value
- Custom WHERE clause

Always generates cleanup SQL and report before executing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.config.app_config import ConnectionConfig
from src.db.connection import DatabaseManager


@dataclass
class CleanupTarget:
    """Definition of what to clean up in one table."""

    table_name: str
    pk_column: str = ""
    pk_range_start: str = ""
    pk_range_end: str = ""
    marker_column: str = ""
    marker_value: str = ""
    custom_where: str = ""
    campaign_id: str = ""

    def build_where_clause(self) -> str:
        """Build the WHERE clause for deletion."""
        conditions = []

        if self.pk_column and self.pk_range_start and self.pk_range_end:
            conditions.append(
                f"`{self.pk_column}` >= '{self.pk_range_start}' "
                f"AND `{self.pk_column}` <= '{self.pk_range_end}'"
            )

        if self.marker_column and self.marker_value:
            conditions.append(f"`{self.marker_column}` = '{self.marker_value}'")

        if self.custom_where:
            conditions.append(f"({self.custom_where})")

        if not conditions:
            raise ValueError(f"No cleanup conditions defined for {self.table_name}")

        return " AND ".join(conditions)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CleanupPlan:
    """Plan for cleaning up test data across tables."""

    campaign_id: str = ""
    targets: list[CleanupTarget] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def add_target(self, target: CleanupTarget) -> None:
        self.targets.append(target)

    def generate_sql(self) -> list[str]:
        """Generate DELETE SQL statements."""
        stmts = []
        for target in self.targets:
            where = target.build_where_clause()
            stmts.append(f"DELETE FROM `{target.table_name}` WHERE {where};")
        return stmts

    def generate_count_sql(self) -> list[str]:
        """Generate COUNT SQL to preview how many rows will be deleted."""
        stmts = []
        for target in self.targets:
            where = target.build_where_clause()
            stmts.append(f"SELECT COUNT(*) AS cnt FROM `{target.table_name}` WHERE {where};")
        return stmts

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "created_at": self.created_at,
            "targets": [t.to_dict() for t in self.targets],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save_sql(self, cleanup_dir: Path) -> Path:
        """Save cleanup SQL to file."""
        cleanup_dir.mkdir(parents=True, exist_ok=True)
        sql_stmts = self.generate_sql()
        path = cleanup_dir / f"cleanup_{self.campaign_id}.sql"
        with path.open("w", encoding="utf-8") as f:
            f.write(f"-- Cleanup SQL for campaign: {self.campaign_id}\n")
            f.write(f"-- Generated at: {self.created_at}\n\n")
            for stmt in sql_stmts:
                f.write(stmt + "\n\n")
        logger.info(f"Cleanup SQL saved to {path}")
        return path


@dataclass
class CleanupReport:
    """Report of cleanup execution."""

    campaign_id: str = ""
    status: str = "pending"
    dry_run: bool = False
    targets_processed: int = 0
    total_rows_deleted: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    error_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    def save(self, reports_dir: Path) -> Path:
        reports_dir.mkdir(parents=True, exist_ok=True)
        prefix = "cleanup_dryrun" if self.dry_run else "cleanup_report"
        path = reports_dir / f"{prefix}_{self.campaign_id}.json"
        with path.open("w", encoding="utf-8") as f:
            f.write(self.to_json())
            f.write("\n")
        return path


def execute_cleanup(
    conn_config: ConnectionConfig,
    plan: CleanupPlan,
    dry_run: bool = True,
    progress_callback=None,
) -> CleanupReport:
    """
    Execute a cleanup plan.

    Args:
        conn_config: Database connection config
        plan: The cleanup plan to execute
        dry_run: If True, only count rows without deleting
        progress_callback: Optional callable(current, total, table_name, count)
    """
    report = CleanupReport(
        campaign_id=plan.campaign_id,
        dry_run=dry_run,
        start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status="running",
    )

    total = len(plan.targets)

    for i, target in enumerate(plan.targets):
        detail = {"table_name": target.table_name, "rows_affected": 0, "success": True, "error": ""}

        db = DatabaseManager(config=conn_config)
        try:
            if not db.connect():
                detail["success"] = False
                detail["error"] = "Connection failed"
                report.details.append(detail)
                continue

            where = target.build_where_clause()

            if dry_run:
                # Count only
                count_sql = f"SELECT COUNT(*) FROM `{target.table_name}` WHERE {where}"
                rows = db.query(count_sql)
                count = int(rows[0][0]) if rows else 0
                detail["rows_affected"] = count
                logger.info(f"[DRY-RUN] {target.table_name}: {count} rows would be deleted")
            else:
                # Actually delete
                delete_sql = f"DELETE FROM `{target.table_name}` WHERE {where}"
                affected = db.execute(delete_sql)
                detail["rows_affected"] = affected
                report.total_rows_deleted += affected
                logger.info(f"[CLEANUP] {target.table_name}: {affected} rows deleted")

            report.targets_processed += 1

        except Exception as exc:
            detail["success"] = False
            detail["error"] = str(exc)
            logger.error(f"Cleanup failed for {target.table_name}: {exc}")
        finally:
            db.disconnect()

        report.details.append(detail)

        if progress_callback:
            progress_callback(i + 1, total, target.table_name, detail["rows_affected"])

    report.status = "completed"
    report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if any(not d["success"] for d in report.details):
        report.status = "partial"
        report.error_summary = "Some tables had errors"

    return report


def build_cleanup_plan_from_report(report_path: Path) -> CleanupPlan | None:
    """Build a cleanup plan from an insertion report file."""
    from src.execute.batch_runner import InsertionReport

    if not report_path.exists():
        return None

    with report_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    campaign_id = data.get("campaign_id", "")
    table_name = data.get("table_name", "")
    pk_start = data.get("pk_range_start", "")
    pk_end = data.get("pk_range_end", "")

    if not table_name or not pk_start or not pk_end:
        return None

    plan = CleanupPlan(campaign_id=campaign_id)
    plan.add_target(CleanupTarget(
        table_name=table_name,
        pk_column="",  # Will need to be filled by caller
        pk_range_start=pk_start,
        pk_range_end=pk_end,
        campaign_id=campaign_id,
    ))

    return plan
