"""
Campaign runner: orchestrates multi-table task execution.

Takes a CampaignPlan and executes each TaskItem in sequence:
1. Select sample for each table
2. Generate data chunks
3. Insert (or dry-run/export)
4. Generate reports and cleanup SQL
"""

from __future__ import annotations

import csv
import json
import re as _re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

import time

from src.config.app_config import AppPaths, ConnectionConfig
from src.utils.timezone import now_jst_compact, now_jst_str
from src.execute.progress import ProgressSnapshot
from src.db.connection import DatabaseManager
from src.execute.batch_runner import BatchConfig, InsertionReport, insert_chunk_files, list_chunk_files
from src.execute.cleanup_runner import CleanupPlan, CleanupTarget
from src.generate.row_builder import generate_to_chunks, resolve_start_values
from src.metadata.models import TableMetadata
from src.metadata.scanner import load_scan_result
from src.plan.models import CampaignPlan, TaskItem
from src.sample.selector import SampleSelection, normalize_sample_for_csv, select_by_pk, select_top_rows


def _build_campaign_dir_name(campaign_id: str, db_name: str) -> str:
    """Build human-readable campaign directory name.

    Example: 20260402_003642_JST__campaign_092bc2__db_cloverit_mock
    """
    ts = now_jst_compact()
    short_id = campaign_id[:8] if len(campaign_id) > 8 else campaign_id
    safe_db = _re.sub(r"[^A-Za-z0-9_]", "_", db_name)[:32]
    return f"{ts}_JST__{short_id}__{safe_db}"


def _build_table_dir_name(task_idx: int, table_name: str,
                           pk_columns: list[str], row_count: int) -> str:
    """Build human-readable table directory name with path length protection.

    Example: 01__t_lock__pk_RESOURCE_NAME__rows_50000
    """
    pk_part = pk_columns[0] if pk_columns else "nopk"
    safe_pk = _re.sub(r"[^A-Za-z0-9_]", "_", pk_part)[:24]
    safe_table = _re.sub(r"[^A-Za-z0-9_]", "_", table_name)[:40]
    return f"{task_idx:02d}__{safe_table}__pk_{safe_pk}__rows_{row_count}"


def _write_table_manifest(
    table_dir: Path,
    report: InsertionReport,
    pk_columns: list[str],
    unique_columns: list[str],
    chunk_files: list[Path],
) -> None:
    """Write table_manifest.json into the table output directory."""
    manifest = {
        "table_name": report.table_name,
        "task_id": report.task_id,
        "campaign_id": report.campaign_id,
        "mode": report.mode,
        "pk_columns": pk_columns,
        "unique_columns": unique_columns,
        "rows_inserted": report.total_rows_inserted,
        "rows_attempted": report.total_rows_attempted,
        "pk_range_start": report.pk_range_start,
        "pk_range_end": report.pk_range_end,
        "status": report.status,
        "start_time": report.start_time,
        "end_time": report.end_time,
        "error_summary": report.error_summary,
        "chunk_count": len(chunk_files),
        "chunk_files": [f.name for f in chunk_files],
        "output_dir": str(table_dir),
    }
    path = table_dir / "table_manifest.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    logger.debug(f"Table manifest: {path}")


def _write_campaign_manifest(
    campaign_dir: Path,
    plan: "CampaignPlan",
    reports: list[InsertionReport],
    conn_config: ConnectionConfig,
) -> None:
    """Write campaign_manifest.json to the campaign root directory."""
    manifest = {
        "campaign_id": plan.campaign_id,
        "db_name": conn_config.database if conn_config else "",
        "db_host": conn_config.host if conn_config else "",
        "db_port": conn_config.port if conn_config else "",
        "total_tables": len(reports),
        "total_rows_inserted": sum(r.total_rows_inserted for r in reports),
        "total_rows_attempted": sum(r.total_rows_attempted for r in reports),
        "failed_tables": sum(1 for r in reports if r.status == "failed"),
        "generated_at": now_jst_str(),
        "tables": [
            {
                "table_name": r.table_name,
                "status": r.status,
                "rows_inserted": r.total_rows_inserted,
                "pk_range_start": r.pk_range_start,
                "pk_range_end": r.pk_range_end,
                "output_dir": r.output_dir,
            }
            for r in reports
        ],
    }
    campaign_dir.mkdir(parents=True, exist_ok=True)
    path = campaign_dir / "campaign_manifest.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Campaign manifest: {path}")


def _write_campaign_summary_csv(
    campaign_dir: Path,
    reports: list[InsertionReport],
) -> None:
    """Write campaign_summary.csv to the campaign root directory."""
    fieldnames = [
        "table_name", "status", "rows_inserted", "rows_attempted",
        "failed_batches", "pk_range_start", "pk_range_end",
        "start_time", "end_time", "error_summary", "output_dir",
    ]
    path = campaign_dir / "campaign_summary.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in reports:
            writer.writerow({
                "table_name": r.table_name,
                "status": r.status,
                "rows_inserted": r.total_rows_inserted,
                "rows_attempted": r.total_rows_attempted,
                "failed_batches": r.failed_batches,
                "pk_range_start": r.pk_range_start,
                "pk_range_end": r.pk_range_end,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "error_summary": r.error_summary,
                "output_dir": r.output_dir,
            })
    logger.info(f"Campaign summary CSV: {path}")


@dataclass
class RunResult:
    """Result of running a complete campaign."""

    campaign_id: str = ""
    reports: list[InsertionReport] = field(default_factory=list)
    cleanup_plan: CleanupPlan = field(default_factory=CleanupPlan)
    success: bool = True
    error_message: str = ""


def run_campaign(
    plan: CampaignPlan,
    conn_config: ConnectionConfig,
    paths: AppPaths,
    scan_result=None,
    progress_callback=None,
    db: DatabaseManager | None = None,
    detail_callback=None,
) -> RunResult:
    """
    Execute a campaign plan.

    Args:
        plan: The campaign plan to execute
        conn_config: Database connection configuration
        paths: Application directory paths
        scan_result: Cached DatabaseScanResult (optional)
        progress_callback: Optional callable(task_index, total_tasks, phase, detail)
            phase: "sample" | "generate" | "insert" | "done"
    """
    plan.status = "running"
    result = RunResult(campaign_id=plan.campaign_id)
    cleanup = CleanupPlan(campaign_id=plan.campaign_id)

    total_tasks = len(plan.tasks)
    db_name = conn_config.database if conn_config else ""
    campaign_dir_name = _build_campaign_dir_name(plan.campaign_id, db_name)
    logger.info(f"Campaign output dir: {campaign_dir_name}")

    for task_idx, task in enumerate(plan.tasks):
        logger.info(f"=== Task {task_idx+1}/{total_tasks}: {task.table_name} ===")

        if progress_callback:
            progress_callback(task_idx + 1, total_tasks, "sample", task.table_name)

        try:
            report = _run_single_task(task, conn_config, paths, scan_result, cleanup,
                                       plan.campaign_id, progress_callback, task_idx, total_tasks,
                                       db=db, detail_callback=detail_callback,
                                       campaign_dir_name=campaign_dir_name)
            result.reports.append(report)

            if report.status == "failed":
                logger.error(f"Task {task.table_name} failed: {report.error_summary}")
                # Continue with next task, don't abort the whole campaign

        except Exception as exc:
            logger.error(f"Task {task.table_name} error: {exc}")
            error_report = InsertionReport(
                table_name=task.table_name,
                task_id=task.task_id,
                campaign_id=plan.campaign_id,
                status="failed",
                error_summary=str(exc),
            )
            result.reports.append(error_report)

    # Write campaign-level evidence files
    campaign_dir = paths.output_dir / campaign_dir_name
    _write_campaign_manifest(campaign_dir, plan, result.reports, conn_config)
    _write_campaign_summary_csv(campaign_dir, result.reports)

    # Save cleanup plan
    cleanup_sql_path = cleanup.save_sql(paths.cleanup_sql_dir)
    logger.info(f"Cleanup SQL saved to {cleanup_sql_path}")

    # Save reports
    for report in result.reports:
        report_path = report.save(paths.reports_dir)
        logger.info(f"Report saved to {report_path}")

    # Save the plan with final status
    all_ok = all(r.status == "completed" for r in result.reports)
    plan.status = "completed" if all_ok else "failed"
    plan.save(paths.plans_dir)

    result.cleanup_plan = cleanup
    result.success = all_ok

    return result


def _run_single_task(
    task: TaskItem,
    conn_config: ConnectionConfig,
    paths: AppPaths,
    scan_result,
    cleanup: CleanupPlan,
    campaign_id: str,
    progress_callback,
    task_idx: int,
    total_tasks: int,
    db: DatabaseManager | None = None,
    detail_callback=None,
    campaign_dir_name: str = "",
) -> InsertionReport:
    """Run a single task item."""

    table_name = task.table_name

    # Get table metadata
    table_meta = None
    if scan_result and table_name in scan_result.tables:
        table_meta = scan_result.tables[table_name]

    # Step 1: Get sample
    sample = _get_sample(task, conn_config, table_meta, db=db)
    if not sample:
        raise RuntimeError(f"Could not get sample for {table_name}")

    template_row = normalize_sample_for_csv(sample.row_data)
    column_order = sample.column_order or list(template_row.keys())

    # Determine PK and unique columns
    pk_columns = table_meta.primary_key_columns if table_meta else []
    unique_columns = table_meta.unique_key_columns if table_meta else []
    json_columns = table_meta.json_columns if table_meta else []

    if not pk_columns and column_order:
        pk_columns = [column_order[0]]

    # Filter unique columns to exclude PK columns
    unique_columns = [c for c in unique_columns if c not in pk_columns]

    # Step 2: Resolve start values
    if progress_callback:
        progress_callback(task_idx + 1, total_tasks, "generate", table_name)

    start_values = {}
    if db is not None:
        start_values = resolve_start_values(db, table_name, template_row, pk_columns + unique_columns)
    else:
        _db = DatabaseManager(config=conn_config)
        try:
            if _db.connect():
                start_values = resolve_start_values(_db, table_name, template_row, pk_columns + unique_columns)
        finally:
            _db.disconnect()

    # Apply pk_config overrides: fixed_start / explicit_range must bypass DB MAX
    if task.pk_config.mode in ("fixed_start", "explicit_range") and task.pk_config.start_value is not None:
        for col in pk_columns:
            start_values[col] = task.pk_config.start_value

    # Step 3: Generate chunks
    table_dir_name = _build_table_dir_name(task_idx + 1, table_name, pk_columns, task.row_count)
    _base = campaign_dir_name if campaign_dir_name else campaign_id
    output_dir = paths.output_dir / _base / table_dir_name
    chunk_size = min(task.batch_size, 10000)

    _gen_start = time.monotonic()

    def _on_chunk_generated(chunk_idx, total_chunks, chunk_rows, generated_total):
        if detail_callback is None:
            return
        elapsed = time.monotonic() - _gen_start
        speed = generated_total / elapsed if elapsed > 0 else 0.0
        remaining = task.row_count - generated_total
        eta = remaining / speed if speed > 0 else -1.0
        overall = ((task_idx - 1) + (generated_total / task.row_count) * 0.5) / total_tasks
        detail_callback(ProgressSnapshot(
            phase="generate",
            task_idx=task_idx,
            total_tasks=total_tasks,
            table_name=table_name,
            total_rows=task.row_count,
            generated_rows=generated_total,
            inserted_rows=0,
            chunk_idx=chunk_idx,
            total_chunks=total_chunks,
            rows_per_sec=speed,
            eta_seconds=eta,
            overall_fraction=overall,
            log_line=f"[generate] {table_name} chunk {chunk_idx}/{total_chunks} ({generated_total:,} rows)",
        ))

    chunk_files = generate_to_chunks(
        template_fieldnames=column_order,
        template_row=template_row,
        pk_columns=pk_columns,
        unique_columns=unique_columns,
        start_values=start_values,
        total_rows=task.row_count,
        chunk_size=chunk_size,
        output_dir=output_dir,
        strategies=task.field_strategies or None,
        marker_column=task.marker_column,
        marker_value=task.marker_value,
        progress_callback=_on_chunk_generated,
        pk_columns_for_filename=pk_columns,
    )

    # Step 4: Insert (or dry-run/export)
    if task.mode == "export":
        # Just generate, no insert
        _now = now_jst_str()
        report = InsertionReport(
            table_name=table_name,
            task_id=task.task_id,
            campaign_id=campaign_id,
            total_rows_attempted=task.row_count,
            total_rows_inserted=0,
            status="completed",
            start_time=_now,
            end_time=_now,
            chunk_files=[str(f) for f in chunk_files],
        )
    else:
        if progress_callback:
            progress_callback(task_idx + 1, total_tasks, "insert", table_name)

        batch_config = BatchConfig(
            batch_size=task.batch_size,
            dry_run=(task.mode == "dry-run"),
        )

        _ins_start = time.monotonic()
        _total_chunks_insert = len(chunk_files)

        def _on_batch_done(batch_idx, total_batches, batch_inserted, total_inserted):
            if detail_callback is None:
                return
            elapsed = time.monotonic() - _ins_start
            speed = total_inserted / elapsed if elapsed > 0 else 0.0
            remaining = task.row_count - total_inserted
            eta = remaining / speed if speed > 0 else -1.0
            overall = ((task_idx - 1) + 0.5 + (total_inserted / task.row_count) * 0.5) / total_tasks
            # Log only every 10 batches or on the last batch
            log = ""
            if total_batches > 0 and (batch_idx % 10 == 0 or batch_idx == total_batches):
                log = (f"[insert] {table_name} batch {batch_idx}/{total_batches} "
                       f"({total_inserted:,} rows, {speed:.0f} rows/s)")
            detail_callback(ProgressSnapshot(
                phase="insert",
                task_idx=task_idx,
                total_tasks=total_tasks,
                table_name=table_name,
                total_rows=task.row_count,
                generated_rows=task.row_count,
                inserted_rows=total_inserted,
                chunk_idx=_total_chunks_insert,
                total_chunks=_total_chunks_insert,
                batch_idx=batch_idx,
                total_batches=total_batches,
                rows_per_sec=speed,
                eta_seconds=eta,
                overall_fraction=overall,
                log_line=log,
            ))

        report = insert_chunk_files(
            conn_config=conn_config,
            table_name=table_name,
            chunk_files=chunk_files,
            json_columns=json_columns,
            batch_config=batch_config,
            campaign_id=campaign_id,
            task_id=task.task_id,
            db=db,
            progress_callback=_on_batch_done,
        )

        # Emit final snapshot so UI shows 100% complete values
        if detail_callback is not None:
            elapsed = time.monotonic() - _ins_start
            speed = report.total_rows_inserted / elapsed if elapsed > 0 else 0.0
            overall = ((task_idx - 1) + 1.0) / total_tasks
            detail_callback(ProgressSnapshot(
                phase="insert",
                task_idx=task_idx,
                total_tasks=total_tasks,
                table_name=table_name,
                total_rows=report.total_rows_attempted,
                generated_rows=report.total_rows_attempted,
                inserted_rows=report.total_rows_inserted,
                chunk_idx=_total_chunks_insert,
                total_chunks=_total_chunks_insert,
                batch_idx=report.total_batches,
                total_batches=report.total_batches,
                rows_per_sec=speed,
                eta_seconds=0.0,
                overall_fraction=overall,
                log_line=f"[insert] {table_name} done: {report.total_rows_inserted:,}/{report.total_rows_attempted:,} rows",
            ))

    # Populate extra metadata on report
    report.pk_columns = pk_columns or []
    report.mode = task.mode
    report.db_name = conn_config.database if conn_config else ""
    report.output_dir = str(output_dir)

    # Write table-level evidence manifest
    _write_table_manifest(output_dir, report, pk_columns, unique_columns, chunk_files)

    # Step 5: Add cleanup target
    if pk_columns and report.pk_range_start and report.pk_range_end:
        cleanup.add_target(CleanupTarget(
            table_name=table_name,
            pk_column=pk_columns[0],
            pk_range_start=report.pk_range_start,
            pk_range_end=report.pk_range_end,
            marker_column=task.marker_column,
            marker_value=task.marker_value,
            campaign_id=campaign_id,
        ))

    if progress_callback:
        progress_callback(task_idx + 1, total_tasks, "done", table_name)

    return report


def _get_sample(task: TaskItem, conn_config: ConnectionConfig,
                table_meta: TableMetadata | None,
                db: DatabaseManager | None = None) -> SampleSelection | None:
    """Retrieve a sample record for the task."""

    _shared = db is not None
    if not _shared:
        db = DatabaseManager(config=conn_config)
        if not db.connect():
            return None

    try:
        if task.sample_method == "pk_lookup" and task.sample_pk_value:
            pk_columns = table_meta.primary_key_columns if table_meta else [db.get_first_column_name(task.table_name)]
            pk_columns = [c for c in pk_columns if c]
            if pk_columns:
                return select_by_pk(db, task.table_name, pk_columns, [task.sample_pk_value])

        if task.sample_method == "where_clause" and task.sample_where:
            from src.sample.selector import select_by_where
            results = select_by_where(db, task.table_name, task.sample_where)
            return results[0] if results else None

        # Default: first row
        results = select_top_rows(db, task.table_name, limit=1)
        return results[0] if results else None

    finally:
        if not _shared:
            db.disconnect()
