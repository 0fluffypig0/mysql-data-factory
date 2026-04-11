#!/usr/bin/env python3
"""
MySQL Data Factory 3.0 — Full Integration Test

Tests:
1. Database connection + schema scan
2. Multi-table campaign with diverse data types (80k total rows)
3. Memory monitoring during generation and insertion
4. Cleanup (delete inserted test data)

Tables selected for coverage:
- t_policy:                94 cols, bigint/datetime/decimal/int/varchar — widest table
- t_calculate_management:  29 cols, decimal precision
- t_email_send_log:        17 cols, longtext fields
- t_achievement_management:22 cols, standard business table

Total: 80,000 rows (20,000 per table)
"""

import os
import sys
import time
import tracemalloc
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.app_config import AppPaths, ConnectionConfig
from src.db.connection import DatabaseManager
from src.metadata.scanner import scan_database
from src.plan.models import CampaignPlan, TaskItem
from src.strategy.pk_planner import PKRangeConfig
from src.workflow.campaign_runner import run_campaign


# ── Config ──
CONN = ConnectionConfig(
    host="160.16.222.138",
    port=3307,
    user="root",
    password="wfD3f46jjdSD583CD2",
    database="ji_test",
)

ROWS_PER_TABLE = 20_000
BATCH_SIZE = 2000
MARKER_VALUE = "V3_TEST_20260411"

TEST_TABLES = [
    "t_policy",                 # 94 cols, all types
    "t_calculate_management",   # 29 cols, decimal
    "t_email_send_log",         # 17 cols, longtext
    "t_achievement_management", # 22 cols, standard
]


def fmt_mb(bytes_val: int) -> str:
    return f"{bytes_val / (1024 * 1024):.1f} MB"


def main():
    tracemalloc.start()
    start_time = time.monotonic()

    print("=" * 70)
    print("MySQL Data Factory 3.0 — Full Integration Test")
    print(f"Tables: {len(TEST_TABLES)}")
    print(f"Rows per table: {ROWS_PER_TABLE:,}")
    print(f"Total rows: {ROWS_PER_TABLE * len(TEST_TABLES):,}")
    print(f"Batch size: {BATCH_SIZE}")
    print("=" * 70)

    # ── Step 1: Connect ──
    print("\n[Step 1] Connecting to database...")
    db = DatabaseManager(config=CONN)
    if not db.connect():
        print("[FAIL] Cannot connect to database")
        return 1
    print(f"[OK] Connected: {CONN.display_safe()}")

    mem_after_connect = tracemalloc.get_traced_memory()
    print(f"  Memory: current={fmt_mb(mem_after_connect[0])}, peak={fmt_mb(mem_after_connect[1])}")

    # ── Step 2: Scan schema ──
    print("\n[Step 2] Scanning database schema...")
    scan_start = time.monotonic()
    scan_result = scan_database(db, progress_callback=lambda c, t, n: None)
    scan_time = time.monotonic() - scan_start
    print(f"[OK] Scanned {len(scan_result.tables)} tables in {scan_time:.1f}s")

    # Verify test tables exist
    for tbl in TEST_TABLES:
        if tbl not in scan_result.tables:
            print(f"[FAIL] Table {tbl} not found in scan results")
            db.disconnect()
            return 1
        meta = scan_result.tables[tbl]
        print(f"  {tbl}: {meta.row_count} rows, PK={meta.primary_key_columns}, "
              f"cols={len(meta.columns)}")

    mem_after_scan = tracemalloc.get_traced_memory()
    print(f"  Memory: current={fmt_mb(mem_after_scan[0])}, peak={fmt_mb(mem_after_scan[1])}")

    # ── Step 3: Build campaign plan ──
    print("\n[Step 3] Building campaign plan...")

    # Find marker columns for each table
    plan = CampaignPlan(database_name="ji_test")
    for tbl in TEST_TABLES:
        meta = scan_result.tables[tbl]
        task = TaskItem(
            table_name=tbl,
            row_count=ROWS_PER_TABLE,
            batch_size=BATCH_SIZE,
            mode="insert",
            sample_method="first_row",
            pk_config=PKRangeConfig(mode="auto_increment_from_max"),
        )
        plan.add_task(task)
        print(f"  Task: {tbl} -> {ROWS_PER_TABLE:,} rows, batch={BATCH_SIZE}")

    print(f"  Campaign ID: {plan.campaign_id}")
    print(f"  Total rows: {plan.total_rows:,}")

    # ── Step 4: Execute campaign ──
    print("\n[Step 4] Executing campaign (this will take a while)...")
    mem_before_exec = tracemalloc.get_traced_memory()
    print(f"  Memory before execution: current={fmt_mb(mem_before_exec[0])}, peak={fmt_mb(mem_before_exec[1])}")

    exec_start = time.monotonic()
    phase_times = {}

    def _on_progress(task_idx, total, phase, detail):
        elapsed = time.monotonic() - exec_start
        mem = tracemalloc.get_traced_memory()
        key = f"{detail}_{phase}"
        if key not in phase_times:
            phase_times[key] = time.monotonic()
            print(f"  [{elapsed:6.1f}s] Task {task_idx}/{total} - {phase}: {detail} "
                  f"(mem: {fmt_mb(mem[0])}, peak: {fmt_mb(mem[1])})")

    paths = AppPaths()
    paths.ensure_all()

    result = run_campaign(
        plan=plan,
        conn_config=CONN,
        paths=paths,
        scan_result=scan_result,
        progress_callback=_on_progress,
        db=db,
    )

    exec_time = time.monotonic() - exec_start
    mem_after_exec = tracemalloc.get_traced_memory()

    print(f"\n  Execution completed in {exec_time:.1f}s")
    print(f"  Memory after execution: current={fmt_mb(mem_after_exec[0])}, peak={fmt_mb(mem_after_exec[1])}")

    # ── Step 5: Results ──
    print("\n[Step 5] Results:")
    print(f"  Campaign ID: {result.campaign_id}")
    print(f"  Success: {result.success}")

    total_inserted = 0
    total_failed = 0
    for report in result.reports:
        status_icon = "OK" if report.status == "completed" else "FAIL"
        print(f"  [{status_icon}] {report.table_name}: "
              f"inserted={report.total_rows_inserted:,}/{report.total_rows_attempted:,}, "
              f"failed_batches={report.failed_batches}, "
              f"PK range={report.pk_range_start}~{report.pk_range_end}")
        total_inserted += report.total_rows_inserted
        total_failed += report.failed_batches
        if report.error_summary:
            print(f"        Error: {report.error_summary}")

    speed = total_inserted / exec_time if exec_time > 0 else 0
    print(f"\n  Total inserted: {total_inserted:,} rows")
    print(f"  Total failed batches: {total_failed}")
    print(f"  Average speed: {speed:,.0f} rows/s")

    # ── Step 6: Cleanup ──
    print("\n[Step 6] Cleaning up test data...")
    cleanup_ok = True
    for report in result.reports:
        if report.pk_range_start and report.pk_range_end and report.pk_columns:
            pk_col = report.pk_columns[0]
            try:
                count_sql = (f"SELECT COUNT(*) FROM `{report.table_name}` "
                            f"WHERE `{pk_col}` BETWEEN %s AND %s")
                rows = db.query(count_sql, (report.pk_range_start, report.pk_range_end))
                count = int(rows[0][0]) if rows else 0

                delete_sql = (f"DELETE FROM `{report.table_name}` "
                             f"WHERE `{pk_col}` BETWEEN %s AND %s")
                deleted = db.execute(delete_sql, (report.pk_range_start, report.pk_range_end))
                print(f"  {report.table_name}: deleted {deleted}/{count} rows "
                      f"(PK {report.pk_range_start}~{report.pk_range_end})")
            except Exception as exc:
                print(f"  {report.table_name}: cleanup FAILED: {exc}")
                cleanup_ok = False

    db.disconnect()

    # ── Summary ──
    total_time = time.monotonic() - start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"  Total time:       {total_time:.1f}s")
    print(f"  Rows inserted:    {total_inserted:,}")
    print(f"  Failed batches:   {total_failed}")
    print(f"  Average speed:    {speed:,.0f} rows/s")
    print(f"  Peak memory:      {fmt_mb(peak_mem)}")
    print(f"  Final memory:     {fmt_mb(current_mem)}")
    print(f"  Cleanup:          {'OK' if cleanup_ok else 'FAILED'}")

    if total_inserted == ROWS_PER_TABLE * len(TEST_TABLES) and total_failed == 0 and cleanup_ok:
        print("\n  >>> ALL TESTS PASSED <<<")
        return 0
    else:
        print("\n  >>> SOME TESTS FAILED <<<")
        return 1


if __name__ == "__main__":
    sys.exit(main())
