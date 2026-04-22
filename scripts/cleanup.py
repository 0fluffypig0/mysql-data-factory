#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 - Cleanup CLI

Delete test data by campaign_id, PK range, or marker column.

Usage:
    python scripts/cleanup.py --campaign-id <id> --dry-run
    python scripts/cleanup.py --campaign-id <id> --execute
    python scripts/cleanup.py --table <name> --pk-column <col> --pk-start <s> --pk-end <e> --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import __version__


def parse_args():
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()

    from src.config.app_config import load_dotenv_file
    load_dotenv_file(env_args.env_file)

    parser = argparse.ArgumentParser(
        description=f"MySQL Data Factory {__version__} - Cleanup test data "
                    "(delete by campaign-id, table PK range, or marker column)"
    )
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to .env file with DB credentials (default: .env in project root)",
    )

    # Target selection
    parser.add_argument(
        "--campaign-id",
        help="Campaign ID to clean up. Reads reports/report_<id>_*.json "
             "and deletes by the recorded PK range. Preferred cleanup path.",
    )
    parser.add_argument(
        "--table",
        help="Single table to clean up (use with --pk-* or --marker-* for the filter).",
    )
    parser.add_argument(
        "--pk-column",
        help="PK column name. Auto-filled from metadata cache if omitted.",
    )
    parser.add_argument("--pk-start", help="PK range start (inclusive).")
    parser.add_argument("--pk-end", help="PK range end (inclusive).")
    parser.add_argument(
        "--marker-column",
        help="Marker column name (e.g. a flag column used to tag test rows).",
    )
    parser.add_argument("--marker-value", help="Value in the marker column to match.")

    # Mode
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Count matching rows without deleting (default).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the rows. Prompts for [y/N] confirmation.",
    )

    # Output
    parser.add_argument(
        "--sql-only",
        action="store_true",
        help="Generate cleanup SQL to sql/cleanup/ and exit; run nothing against the DB.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from src.config.app_config import ConnectionConfig, AppPaths
    from src.execute.cleanup_runner import (
        CleanupPlan, CleanupTarget, CleanupReport, execute_cleanup,
    )
    from src.report.history import load_report

    conn = ConnectionConfig.from_env()
    paths = AppPaths()
    paths.ensure_all()

    plan = CleanupPlan(campaign_id=args.campaign_id or "manual")

    if args.campaign_id:
        # Build from reports
        for report_file in paths.reports_dir.glob(f"report_{args.campaign_id}_*.json"):
            data = load_report(report_file)
            table_name = data.get("table_name", "")
            pk_start = data.get("pk_range_start", "")
            pk_end = data.get("pk_range_end", "")
            if table_name and pk_start and pk_end:
                plan.add_target(CleanupTarget(
                    table_name=table_name,
                    pk_column=args.pk_column or "",
                    pk_range_start=pk_start,
                    pk_range_end=pk_end,
                    campaign_id=args.campaign_id,
                ))

    elif args.table:
        target = CleanupTarget(
            table_name=args.table,
            pk_column=args.pk_column or "",
            pk_range_start=args.pk_start or "",
            pk_range_end=args.pk_end or "",
            marker_column=args.marker_column or "",
            marker_value=args.marker_value or "",
        )
        plan.add_target(target)

    else:
        print("[ERROR] Specify --campaign-id or --table")
        return 1

    if not plan.targets:
        print("[ERROR] No cleanup targets found.")
        return 1

    # Fill PK columns from metadata cache if available
    from src.metadata.scanner import load_scan_result
    scan_result = load_scan_result(paths.metadata_cache_dir, conn.database)
    if scan_result:
        for target in plan.targets:
            if not target.pk_column and target.table_name in scan_result.tables:
                meta = scan_result.tables[target.table_name]
                if meta.primary_key_columns:
                    target.pk_column = meta.primary_key_columns[0]

    # SQL only mode
    if args.sql_only:
        sql_path = plan.save_sql(paths.cleanup_sql_dir)
        print(f"[OK] Cleanup SQL generated: {sql_path}")
        for stmt in plan.generate_sql():
            print(f"  {stmt}")
        return 0

    # Count preview
    print("Cleanup targets:")
    for target in plan.targets:
        print(f"  {target.table_name}: {target.build_where_clause()}")

    dry_run = not args.execute
    mode_label = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\nMode: {mode_label}")

    if not dry_run:
        confirm = input("This will DELETE data. Continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return 0

    # Execute
    report = execute_cleanup(conn, plan, dry_run=dry_run)

    # Save
    report_path = report.save(paths.reports_dir)
    sql_path = plan.save_sql(paths.cleanup_sql_dir)

    print(f"\n[{mode_label}] Results:")
    for detail in report.details:
        status_icon = "OK" if detail["success"] else "FAIL"
        print(f"  [{status_icon}] {detail['table_name']}: {detail['rows_affected']} rows")
        if detail.get("error"):
            print(f"       Error: {detail['error']}")

    print(f"\nReport: {report_path}")
    print(f"SQL: {sql_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

