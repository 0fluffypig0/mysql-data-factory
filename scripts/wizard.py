#!/usr/bin/env python3
"""
MySQL Data Factory 2.0 - CLI Wizard

Interactive command-line wizard for configuring and executing
multi-table data generation campaigns.

Usage:
    python scripts/wizard.py [--env-file .env]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser(description="MySQL Data Factory 2.0 CLI Wizard")
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from src.config.app_config import load_dotenv_file, ConnectionConfig, AppPaths
    from src.db.connection import DatabaseManager
    from src.metadata.scanner import scan_database, save_scan_result, load_scan_result
    from src.plan.models import CampaignPlan, TaskItem
    from src.workflow.campaign_runner import run_campaign

    load_dotenv_file(args.env_file)
    paths = AppPaths()
    paths.ensure_all()

    print("=" * 60)
    print("  MySQL Data Factory 2.0 - CLI Wizard")
    print("=" * 60)
    print()

    # Step 1: Connection
    conn = ConnectionConfig.from_env()
    print(f"Connection: {conn.display_safe()}")
    db = DatabaseManager(config=conn)
    if not db.connect():
        print("[ERROR] Cannot connect to database.")
        return 1
    db.disconnect()
    print("[OK] Connection successful.\n")

    # Step 2: Scan or load cache
    cached = load_scan_result(paths.metadata_cache_dir, conn.database)
    if cached:
        print(f"Found cached scan from {cached.scan_time} ({len(cached.tables)} tables)")
        choice = input("Use cached scan? [Y/n]: ").strip().lower()
        if choice == "n":
            cached = None

    if not cached:
        print("Scanning database...")
        db = DatabaseManager(config=conn)
        db.connect()
        cached = scan_database(db)
        db.disconnect()
        save_scan_result(cached, paths.metadata_cache_dir)
        print(f"[OK] Scanned {len(cached.tables)} tables.\n")

    scan_result = cached

    # Step 3: Select tables
    print("Available tables:")
    table_names = scan_result.table_names
    for i, name in enumerate(table_names, 1):
        meta = scan_result.tables[name]
        print(f"  {i:3d}. {name} (rows={meta.row_count}, pk={meta.pk_display})")

    print()
    selection = input("Enter table numbers (comma-separated, e.g. 1,3,5) or 'all': ").strip()
    if selection.lower() == "all":
        selected = table_names
    else:
        indices = [int(x.strip()) - 1 for x in selection.split(",") if x.strip().isdigit()]
        selected = [table_names[i] for i in indices if 0 <= i < len(table_names)]

    if not selected:
        print("[ERROR] No tables selected.")
        return 1

    # Step 4: Configure tasks
    plan = CampaignPlan(database_name=conn.database)

    for table_name in selected:
        print(f"\n--- Configure: {table_name} ---")
        meta = scan_result.tables.get(table_name)

        row_count = input(f"  Row count [1000]: ").strip()
        row_count = int(row_count) if row_count else 1000

        batch_size = input(f"  Batch size [1000]: ").strip()
        batch_size = int(batch_size) if batch_size else 1000

        mode = input(f"  Mode (insert/dry-run/export) [insert]: ").strip() or "insert"

        sample_pk = input(f"  Sample PK value (or Enter for first row): ").strip()

        marker_value = input(f"  Test marker value (or Enter for none): ").strip()
        marker_column = ""
        if marker_value and meta and meta.marker_columns:
            marker_column = meta.marker_columns[0]
            print(f"    Using marker column: {marker_column}")

        task = TaskItem(
            table_name=table_name,
            row_count=row_count,
            batch_size=batch_size,
            mode=mode,
            sample_pk_value=sample_pk,
            sample_method="pk_lookup" if sample_pk else "first_row",
            marker_column=marker_column,
            marker_value=marker_value,
        )
        plan.add_task(task)

    # Step 5: Confirm
    print("\n" + "=" * 60)
    print(plan.summary())
    print("=" * 60)
    confirm = input("\nProceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Cancelled.")
        return 0

    # Step 6: Execute
    print("\nExecuting campaign...")
    result = run_campaign(
        plan=plan,
        conn_config=conn,
        paths=paths,
        scan_result=scan_result,
        progress_callback=lambda idx, total, phase, detail: print(f"  [{idx}/{total}] {phase}: {detail}"),
    )

    # Step 7: Summary
    print("\n" + "=" * 60)
    print("  Execution Complete")
    print("=" * 60)
    for report in result.reports:
        status_icon = "OK" if report.status == "completed" else "FAIL"
        print(f"  [{status_icon}] {report.table_name}: "
              f"{report.total_rows_inserted}/{report.total_rows_attempted} inserted")
        if report.pk_range_start:
            print(f"       PK range: {report.pk_range_start} ~ {report.pk_range_end}")

    print(f"\nReports: {paths.reports_dir}")
    print(f"Cleanup SQL: {paths.cleanup_sql_dir}")
    print(f"Plans: {paths.plans_dir}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
