"""
Database metadata scanner.

Scans all tables in a database and produces a DatabaseScanResult
that can be cached and reused across sessions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.db.connection import DatabaseManager
from src.metadata.models import (
    ColumnMetadata,
    DatabaseScanResult,
    TableMetadata,
)

# Time-related SQL types
TIME_TYPES = {"datetime", "timestamp", "date", "time", "year"}

# Column names that might serve as test data markers
MARKER_PATTERNS = {
    "remark", "remarks", "source", "created_by", "updated_by",
    "memo", "comment", "comments", "note", "notes", "description",
    "tag", "tags", "flag", "test_flag", "data_source",
}


def scan_table(db: DatabaseManager, table_name: str) -> TableMetadata:
    """Scan a single table and return its metadata."""

    pk_columns = db.get_primary_key_columns(table_name)
    unique_columns = db.get_unique_key_columns(table_name)
    json_columns = db.get_json_columns(table_name)
    auto_inc_columns = db.get_auto_increment_columns(table_name)
    column_order = db.get_column_names(table_name)
    column_info_list = db.get_column_info(table_name)

    try:
        row_count = db.count_rows(table_name)
    except Exception:
        row_count = -1

    # Get max PK value if there's a single PK column
    max_pk_value = None
    if len(pk_columns) == 1:
        try:
            max_pk_value = db.get_max_pk_value(table_name, pk_columns[0])
            if max_pk_value is not None:
                max_pk_value = str(max_pk_value)
        except Exception:
            pass

    # Build column metadata
    columns: list[ColumnMetadata] = []
    time_columns: list[str] = []
    marker_columns: list[str] = []

    for col_info in column_info_list:
        col_name = col_info["COLUMN_NAME"]
        data_type = col_info["DATA_TYPE"].lower()
        is_time = data_type in TIME_TYPES
        is_marker = col_name.lower() in MARKER_PATTERNS
        is_json = data_type == "json"

        col_meta = ColumnMetadata(
            name=col_name,
            data_type=data_type,
            column_type=col_info.get("COLUMN_TYPE", data_type),
            is_nullable=col_info.get("IS_NULLABLE", "YES") == "YES",
            column_default=str(col_info["COLUMN_DEFAULT"]) if col_info.get("COLUMN_DEFAULT") is not None else None,
            is_primary_key=col_name in pk_columns,
            is_unique_key=col_name in unique_columns,
            is_auto_increment=col_name in auto_inc_columns,
            is_json=is_json,
            is_time_field=is_time,
            is_potential_marker=is_marker,
            max_length=col_info.get("CHARACTER_MAXIMUM_LENGTH"),
            numeric_precision=col_info.get("NUMERIC_PRECISION"),
            numeric_scale=col_info.get("NUMERIC_SCALE"),
        )
        columns.append(col_meta)

        if is_time:
            time_columns.append(col_name)
        if is_marker:
            marker_columns.append(col_name)

    return TableMetadata(
        table_name=table_name,
        database_name=db.database,
        columns=columns,
        primary_key_columns=pk_columns,
        unique_key_columns=unique_columns,
        json_columns=json_columns,
        auto_increment_columns=auto_inc_columns,
        time_columns=time_columns,
        marker_columns=marker_columns,
        column_order=column_order,
        row_count=row_count,
        max_pk_value=max_pk_value,
    )


def scan_database(db: DatabaseManager, table_filter: list[str] | None = None,
                  progress_callback=None) -> DatabaseScanResult:
    """
    Scan all tables in the database.

    Args:
        db: Connected DatabaseManager
        table_filter: If provided, only scan these tables
        progress_callback: Optional callable(current, total, table_name)
    """

    all_tables = db.show_tables()
    if table_filter:
        tables_to_scan = [t for t in all_tables if t in table_filter]
    else:
        tables_to_scan = all_tables

    total = len(tables_to_scan)
    logger.info(f"Scanning {total} tables in {db.database}...")

    result = DatabaseScanResult(database_name=db.database)

    for i, table_name in enumerate(tables_to_scan):
        logger.info(f"  [{i+1}/{total}] Scanning {table_name}...")
        if progress_callback:
            progress_callback(i + 1, total, table_name)
        try:
            meta = scan_table(db, table_name)
            result.tables[table_name] = meta
        except Exception as exc:
            logger.warning(f"  Failed to scan {table_name}: {exc}")
            result.tables[table_name] = TableMetadata(
                table_name=table_name,
                database_name=db.database,
                notes=f"scan_error: {exc}",
            )

    logger.success(f"Scan complete: {len(result.tables)} tables scanned")
    return result


# --- Cache I/O ---

def _sanitize_db_name_for_filename(database_name: str) -> str:
    """
    Turn a database name into a safe filename fragment.

    MySQL DB names are normally simple, but SQLite "database names" are file
    paths which can contain drive letters (`C:\\...`), backslashes, colons,
    and forward slashes — none of which are legal in a Windows filename.
    Strip the path down to its stem and replace anything unusual with `_`.
    """
    import re
    # For SQLite-style paths, grab the final component without extension
    # so a DB at `data/mydata.sqlite3` caches as `db_scan_mydata.json`.
    if "/" in database_name or "\\" in database_name or ":" in database_name:
        stem = Path(database_name).stem or "sqlite_db"
        database_name = stem
    return re.sub(r"[^A-Za-z0-9_.-]", "_", database_name)


def get_cache_path(cache_dir: Path, database_name: str) -> Path:
    return cache_dir / f"db_scan_{_sanitize_db_name_for_filename(database_name)}.json"


def save_scan_result(result: DatabaseScanResult, cache_dir: Path) -> Path:
    """Save scan result to metadata cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = get_cache_path(cache_dir, result.database_name)
    with cache_path.open("w", encoding="utf-8") as f:
        f.write(result.to_json())
        f.write("\n")
    logger.info(f"Scan result saved to {cache_path}")
    return cache_path


def load_scan_result(cache_dir: Path, database_name: str) -> DatabaseScanResult | None:
    """Load cached scan result. Returns None if not found."""
    cache_path = get_cache_path(cache_dir, database_name)
    if not cache_path.exists():
        return None
    with cache_path.open("r", encoding="utf-8") as f:
        return DatabaseScanResult.from_json(f.read())


def list_cached_databases(cache_dir: Path) -> list[str]:
    """List database names that have cached scan results."""
    if not cache_dir.exists():
        return []
    results = []
    for f in cache_dir.glob("db_scan_*.json"):
        name = f.stem.replace("db_scan_", "")
        results.append(name)
    return sorted(results)
