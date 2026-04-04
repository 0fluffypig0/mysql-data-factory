"""
Report history management.

Lists, loads, and summarizes historical campaign plans and execution reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class HistoryEntry:
    """A single history entry (plan or report)."""

    file_path: str
    campaign_id: str = ""
    entry_type: str = ""   # plan | report | cleanup_report | cleanup_sql
    table_name: str = ""
    db_name: str = ""
    status: str = ""
    created_at: str = ""   # JST string
    mode: str = ""         # insert | dry-run | export
    pk_columns: str = ""   # comma-separated
    pk_start: str = ""
    pk_end: str = ""
    rows_inserted: int = 0
    rows_attempted: int = 0
    run_id: str = ""
    report_path: str = ""
    cleanup_sql_path: str = ""
    summary: str = ""


def list_plans(plans_dir: Path) -> list[HistoryEntry]:
    """List all campaign plan files."""
    entries = []
    if not plans_dir.exists():
        return entries

    for f in sorted(plans_dir.glob("campaign_*.json"), reverse=True):
        try:
            with f.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries.append(HistoryEntry(
                file_path=str(f),
                campaign_id=data.get("campaign_id", ""),
                entry_type="plan",
                db_name=data.get("database_name", ""),
                status=data.get("status", ""),
                created_at=data.get("created_at", ""),
                summary=f"{data.get('table_count', 0)} tables, {data.get('total_rows', 0)} rows",
            ))
        except Exception:
            continue
    return entries


def list_reports(reports_dir: Path, cleanup_sql_dir: Path | None = None) -> list[HistoryEntry]:
    """List all execution report files with full detail."""
    entries = []
    if not reports_dir.exists():
        return entries

    for f in sorted(reports_dir.glob("report_*.json"), reverse=True):
        try:
            with f.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            cid = data.get("campaign_id", "")
            pk_cols = data.get("pk_columns", [])
            if isinstance(pk_cols, list):
                pk_cols_str = ", ".join(pk_cols)
            else:
                pk_cols_str = str(pk_cols)
            # Locate matching cleanup SQL if dir provided
            cleanup_path = ""
            if cleanup_sql_dir:
                sql_file = cleanup_sql_dir / f"cleanup_{cid}.sql"
                if sql_file.exists():
                    cleanup_path = str(sql_file)
            entries.append(HistoryEntry(
                file_path=str(f),
                campaign_id=cid,
                entry_type="report",
                table_name=data.get("table_name", ""),
                db_name=data.get("db_name", ""),
                status=data.get("status", ""),
                created_at=data.get("start_time", ""),
                mode=data.get("mode", "insert"),
                pk_columns=pk_cols_str,
                pk_start=str(data.get("pk_range_start", "")),
                pk_end=str(data.get("pk_range_end", "")),
                rows_inserted=data.get("total_rows_inserted", 0),
                rows_attempted=data.get("total_rows_attempted", 0),
                run_id=data.get("run_id", ""),
                report_path=str(f),
                cleanup_sql_path=cleanup_path,
                summary=f"{data.get('total_rows_inserted', 0)}/{data.get('total_rows_attempted', 0)} inserted",
            ))
        except Exception:
            continue
    return entries


def list_cleanup_reports(reports_dir: Path) -> list[HistoryEntry]:
    """List cleanup execution report files."""
    entries = []
    if not reports_dir.exists():
        return entries

    for f in sorted(reports_dir.glob("cleanup_report_*.json"), reverse=True):
        try:
            with f.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries.append(HistoryEntry(
                file_path=str(f),
                campaign_id=data.get("campaign_id", ""),
                entry_type="cleanup_report",
                status=data.get("status", ""),
                created_at=data.get("start_time", ""),
                summary=f"{'DRY-RUN' if data.get('dry_run') else 'EXECUTED'}: {data.get('total_rows_deleted', 0)} rows",
            ))
        except Exception:
            continue
    return entries


def list_cleanup_sql(cleanup_dir: Path) -> list[HistoryEntry]:
    """List cleanup SQL files."""
    entries = []
    if not cleanup_dir.exists():
        return entries

    for f in sorted(cleanup_dir.glob("cleanup_*.sql"), reverse=True):
        entries.append(HistoryEntry(
            file_path=str(f),
            campaign_id=f.stem.replace("cleanup_", ""),
            entry_type="cleanup_sql",
            summary=f.name,
        ))
    return entries


def load_report(path: Path) -> dict[str, Any]:
    """Load a JSON report file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
