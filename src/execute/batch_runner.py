"""
Batch insertion runner.

Inserts data from chunk CSV files into the database in batches.
Each batch gets its own short-lived connection.
Supports dry-run, throttling, error limits, and per-batch reporting.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from src.config.app_config import ConnectionConfig
from src.db.connection import DatabaseManager


@dataclass
class BatchConfig:
    """Configuration for batch insertion."""

    batch_size: int = 1000
    commit_per_batch: bool = True
    throttle_ms: int = 0
    max_errors: int = 5
    stop_on_error: bool = True
    dry_run: bool = False
    skip_db_check: bool = False
    # Insertion mode: "insert" (default, per-batch INSERT via executemany)
    # or "load_data" (LOAD DATA LOCAL INFILE per chunk file — much faster,
    # requires server-side `local_infile = ON`).
    insert_mode: str = "insert"
    # When True (default), chunk files are kept after successful insertion
    # for troubleshooting / export workflows. When False, each chunk file
    # is deleted once its rows are loaded — useful on bastion hosts with
    # small local disks.
    keep_chunks: bool = True


@dataclass
class BatchResult:
    """Result for a single batch."""

    batch_index: int = 0
    rows_attempted: int = 0
    rows_inserted: int = 0
    success: bool = True
    error_message: str = ""


@dataclass
class InsertionReport:
    """Report for a complete table insertion."""

    table_name: str = ""
    task_id: str = ""
    run_id: str = ""
    campaign_id: str = ""
    total_rows_attempted: int = 0
    total_rows_inserted: int = 0
    total_batches: int = 0
    failed_batches: int = 0
    batch_results: list[BatchResult] = field(default_factory=list)
    pk_range_start: str = ""
    pk_range_end: str = ""
    pk_columns: list[str] = field(default_factory=list)
    mode: str = "insert"  # insert | dry-run | export
    db_name: str = ""
    status: str = "pending"  # pending | running | completed | failed
    start_time: str = ""
    end_time: str = ""
    error_summary: str = ""
    chunk_files: list[str] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    def save(self, reports_dir: Path) -> Path:
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"report_{self.campaign_id}_{self.table_name}.json"
        with path.open("w", encoding="utf-8") as f:
            f.write(self.to_json())
            f.write("\n")
        return path


def read_chunk_csv(file_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a chunk CSV file."""
    with file_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def list_chunk_files(input_path: Path) -> list[Path]:
    """List chunk CSV or TSV files from a file or directory."""
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            p for p in input_path.iterdir()
            if p.is_file() and p.suffix.lower() in (".csv", ".tsv")
        )
    return []


def _first_tsv_first_col(path: Path) -> str:
    """Read the first line of a TSV and return the first tab-separated field (PK)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            line = f.readline().rstrip("\n")
        if not line:
            return ""
        val = line.split("\t", 1)[0]
        return "" if val == "\\N" else val
    except Exception:
        return ""


def _last_tsv_first_col(path: Path) -> str:
    """Scan a TSV and return the first field of the last non-empty line."""
    last = ""
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line:
                    last = line.split("\t", 1)[0]
    except Exception:
        return ""
    return "" if last == "\\N" else last


def _count_tsv_rows(path: Path) -> int:
    """Count non-empty lines in a TSV file."""
    try:
        n = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.rstrip("\n"):
                    n += 1
        return n
    except Exception:
        return 0


def _normalize_value(value: str, column_name: str, json_columns: list[str]) -> Any:
    """Normalize a CSV string value for database insertion."""
    if value == "" or value is None:
        return None
    if column_name in json_columns:
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def _is_retryable_error(exc: Exception) -> bool:
    """Check if a database error is retryable (connection lost etc.)."""
    msg = str(exc).lower()
    retryable_patterns = [
        "lost connection", "gone away", "broken pipe",
        "connection reset", "server has gone away",
    ]
    return any(p in msg for p in retryable_patterns)


def insert_chunk_files(
    conn_config: ConnectionConfig,
    table_name: str,
    chunk_files: list[Path],
    json_columns: list[str] | None = None,
    batch_config: BatchConfig | None = None,
    campaign_id: str = "",
    task_id: str = "",
    progress_callback=None,
    db: DatabaseManager | None = None,
) -> InsertionReport:
    """
    Insert data from chunk files (CSV for INSERT mode, TSV for LOAD DATA mode).

    When `db` is provided, uses that shared connection for all batches
    (required for bastion host one-time credentials).
    Otherwise falls back to short-lived connections per batch.
    """
    from datetime import datetime

    if batch_config is None:
        batch_config = BatchConfig()
    if json_columns is None:
        json_columns = []

    # Dispatch to LOAD DATA branch when requested. The INSERT path below is
    # unchanged to preserve behavior for all existing callers.
    # Guard: LOAD DATA LOCAL INFILE is MySQL-only; silently fall back to the
    # INSERT path for any other dialect so direct callers of this function
    # (scripts, tests) get graceful behavior instead of a hard SQL error.
    if batch_config.insert_mode == "load_data" and not batch_config.dry_run:
        if not conn_config.is_mysql():
            logger.warning(
                f"insert_mode='load_data' ignored: dialect={conn_config.dialect} "
                "does not support LOAD DATA LOCAL INFILE. Using INSERT path."
            )
        else:
            return _insert_via_load_data(
                conn_config=conn_config,
                table_name=table_name,
                chunk_files=chunk_files,
                batch_config=batch_config,
                campaign_id=campaign_id,
                task_id=task_id,
                progress_callback=progress_callback,
                db=db,
            )

    report = InsertionReport(
        table_name=table_name,
        task_id=task_id,
        campaign_id=campaign_id,
        run_id=f"{campaign_id}_{task_id}" if campaign_id else task_id,
        status="running",
        start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        chunk_files=[str(f) for f in chunk_files],
    )

    # ── Stream chunks one-by-one to avoid loading all data into memory ──
    # First pass: read fieldnames from the first chunk and count total rows
    fieldnames: list[str] = []
    total_rows_count = 0
    for cf in chunk_files:
        fn, rows = read_chunk_csv(cf)
        if not fieldnames:
            fieldnames = fn
        total_rows_count += len(rows)

    report.total_rows_attempted = total_rows_count

    if total_rows_count == 0:
        report.status = "completed"
        report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return report

    # Track PK range (first and last value only — no list accumulation)
    pk_first: str = ""
    pk_last: str = ""

    # Build SQL — dialect-aware quoting so the same code path works for
    # MySQL (backticks) and SQLite (double-quotes).
    q = conn_config.quote_identifier
    columns_sql = ", ".join(q(c) for c in fieldnames)
    placeholders = ", ".join(["%s"] * len(fieldnames))
    insert_sql = f"INSERT INTO {q(table_name)} ({columns_sql}) VALUES ({placeholders})"

    # Process chunk files one at a time (streaming)
    batch_size = batch_config.batch_size
    # Estimate total batches for progress reporting
    total_batches = 0
    for cf in chunk_files:
        # Each chunk file may produce multiple batches
        fn, rows = read_chunk_csv(cf)
        total_batches += max(1, (len(rows) + batch_size - 1) // batch_size)

    report.total_batches = total_batches
    error_count = 0
    global_batch_idx = 0
    stop_flag = False

    for cf in chunk_files:
        if stop_flag:
            break

        # Read one chunk file at a time — memory only holds one chunk
        _, chunk_rows = read_chunk_csv(cf)
        if not chunk_rows:
            continue

        # Split chunk into batches
        for batch_start in range(0, len(chunk_rows), batch_size):
            if stop_flag:
                break

            batch_rows = chunk_rows[batch_start:batch_start + batch_size]
            global_batch_idx += 1

            batch_result = BatchResult(
                batch_index=global_batch_idx,
                rows_attempted=len(batch_rows),
            )

            if batch_config.dry_run:
                batch_result.rows_inserted = len(batch_rows)
                batch_result.success = True
                report.batch_results.append(batch_result)
                report.total_rows_inserted += len(batch_rows)
                if progress_callback:
                    progress_callback(global_batch_idx, total_batches, len(batch_rows), report.total_rows_inserted)
                continue

            # Prepare params
            params_list = []
            for row in batch_rows:
                params = tuple(
                    _normalize_value(row.get(col, ""), col, json_columns)
                    for col in fieldnames
                )
                params_list.append(params)

            # Track PK range (first and last only)
            if fieldnames:
                if not pk_first:
                    pk_first = batch_rows[0].get(fieldnames[0], "")
                pk_last = batch_rows[-1].get(fieldnames[0], "")

            # Insert — use shared connection if provided, else short-lived per batch
            _shared = db is not None
            retry_count = 0
            max_retries = 0 if _shared else 1
            while retry_count <= max_retries:
                _db = db if _shared else DatabaseManager(config=conn_config)
                try:
                    if not _shared and not _db.connect():
                        raise RuntimeError("Failed to connect to database")
                    affected = _db.executemany(insert_sql, params_list)
                    batch_result.rows_inserted = affected
                    batch_result.success = True
                    report.total_rows_inserted += affected
                    break
                except Exception as exc:
                    if not _shared and retry_count < max_retries and _is_retryable_error(exc):
                        retry_count += 1
                        logger.warning(f"Batch {global_batch_idx} connection error, retrying... ({exc})")
                        time.sleep(1)
                        continue
                    batch_result.success = False
                    batch_result.error_message = str(exc)
                    error_count += 1
                    logger.error(f"Batch {global_batch_idx} failed: {exc}")
                    break
                finally:
                    if not _shared:
                        _db.disconnect()

            report.batch_results.append(batch_result)

            if progress_callback:
                progress_callback(global_batch_idx, total_batches,
                                  batch_result.rows_inserted, report.total_rows_inserted)

            if not batch_result.success and batch_config.stop_on_error:
                report.error_summary = f"Stopped at batch {global_batch_idx}: {batch_result.error_message}"
                stop_flag = True

            if error_count >= batch_config.max_errors:
                report.error_summary = f"Max errors ({batch_config.max_errors}) reached"
                stop_flag = True

            if batch_config.throttle_ms > 0:
                time.sleep(batch_config.throttle_ms / 1000.0)

    # PK range
    if pk_first:
        report.pk_range_start = pk_first
    if pk_last:
        report.pk_range_end = pk_last

    report.failed_batches = sum(1 for b in report.batch_results if not b.success)
    report.status = "completed" if report.failed_batches == 0 else "failed"
    report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return report


def _insert_via_load_data(
    conn_config: ConnectionConfig,
    table_name: str,
    chunk_files: list[Path],
    batch_config: BatchConfig,
    campaign_id: str,
    task_id: str,
    progress_callback,
    db: DatabaseManager | None,
) -> InsertionReport:
    """
    Fast-insert path using LOAD DATA LOCAL INFILE, one statement per chunk file.

    Each chunk file = one batch from the report's perspective.
    Chunk files are expected to be TSV in MySQL-native format
    (produced by row_builder._write_load_data_tsv).

    If `batch_config.keep_chunks` is False, each file is deleted right after
    a successful load — this caps peak disk use at a single chunk file,
    which matters on bastion hosts with small local disks.
    """
    from datetime import datetime

    from src.execute.loader import load_data_chunk

    report = InsertionReport(
        table_name=table_name,
        task_id=task_id,
        campaign_id=campaign_id,
        run_id=f"{campaign_id}_{task_id}" if campaign_id else task_id,
        status="running",
        mode="insert",
        start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        chunk_files=[str(f) for f in chunk_files],
    )

    if not chunk_files:
        report.status = "completed"
        report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return report

    # Shared connection is required for LOAD DATA mode — reconnecting between
    # chunks would pay the handshake cost repeatedly and, on bastion hosts,
    # burn one-time credentials.
    _shared = db is not None
    _db = db if _shared else DatabaseManager(config=conn_config)
    if not _shared and not _db.connect():
        report.status = "failed"
        report.error_summary = "Failed to connect to database"
        report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return report

    # Column list must match the TSV column order. Both were derived from
    # INFORMATION_SCHEMA.COLUMNS ORDER BY ORDINAL_POSITION, so this is stable.
    try:
        columns = _db.get_column_names(table_name)
    except Exception as exc:
        report.status = "failed"
        report.error_summary = f"Could not read columns for {table_name}: {exc}"
        report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not _shared:
            _db.disconnect()
        return report

    if not columns:
        report.status = "failed"
        report.error_summary = f"Table {table_name} has no columns"
        report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not _shared:
            _db.disconnect()
        return report

    total_batches = len(chunk_files)
    report.total_batches = total_batches

    # Pre-count attempted rows so the UI progress bar has a meaningful total.
    total_attempt = 0
    for cf in chunk_files:
        total_attempt += _count_tsv_rows(cf)
    report.total_rows_attempted = total_attempt

    pk_first_val = ""
    pk_last_val = ""
    error_count = 0

    try:
        for i, cf in enumerate(chunk_files, start=1):
            batch_result = BatchResult(batch_index=i)
            # Attempted-rows comes from line count; we don't normalize empties.
            chunk_rows = _count_tsv_rows(cf)
            batch_result.rows_attempted = chunk_rows

            # Track PK range via cheap file peek (first col of first/last line).
            if i == 1:
                pk_first_val = _first_tsv_first_col(cf)
            pk_last_val = _last_tsv_first_col(cf) or pk_last_val

            try:
                affected = load_data_chunk(_db, table_name, columns, cf)
                batch_result.rows_inserted = affected
                batch_result.success = True
                report.total_rows_inserted += affected
                logger.success(
                    f"LOAD DATA {i}/{total_batches}: {cf.name} → {affected} rows"
                )
            except Exception as exc:
                batch_result.success = False
                batch_result.error_message = str(exc)
                error_count += 1
                logger.error(f"LOAD DATA failed for {cf.name}: {exc}")

            report.batch_results.append(batch_result)

            if progress_callback:
                progress_callback(
                    i, total_batches, batch_result.rows_inserted,
                    report.total_rows_inserted,
                )

            # Delete chunk file after successful load, if keep_chunks=False.
            # Leave failed chunks on disk for debugging.
            if batch_result.success and not batch_config.keep_chunks:
                try:
                    cf.unlink()
                    logger.debug(f"Deleted loaded chunk: {cf.name}")
                except Exception as exc:
                    logger.warning(f"Could not delete {cf.name}: {exc}")

            if not batch_result.success and batch_config.stop_on_error:
                report.error_summary = (
                    f"Stopped at chunk {i}: {batch_result.error_message}"
                )
                break

            if error_count >= batch_config.max_errors:
                report.error_summary = (
                    f"Max errors ({batch_config.max_errors}) reached"
                )
                break

            if batch_config.throttle_ms > 0:
                time.sleep(batch_config.throttle_ms / 1000.0)
    finally:
        if not _shared:
            _db.disconnect()

    if pk_first_val:
        report.pk_range_start = pk_first_val
    if pk_last_val:
        report.pk_range_end = pk_last_val

    report.failed_batches = sum(1 for b in report.batch_results if not b.success)
    report.status = "completed" if report.failed_batches == 0 else "failed"
    report.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return report
