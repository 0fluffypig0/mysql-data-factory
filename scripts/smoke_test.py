#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 - Smoke Test

Quick validation that the core pipeline works:
1. Connect to database
2. Scan metadata
3. Generate preview data
4. (Optional) Insert small batch

Usage:
    python scripts/smoke_test.py [--env-file .env] [--insert]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Smoke test for MySQL Data Factory {__version__}"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with DB credentials (default: .env in project root)",
    )
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Actually insert the generated rows. Omit for preview-only (safe) mode.",
    )
    parser.add_argument(
        "--table",
        help="Optional. Target table name. If omitted, auto-picks the first table "
             "that has data and a primary key.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=5,
        help="Number of rows to generate (default: 5). "
             "For stress testing use pressure_test_100k.py instead.",
    )
    parser.add_argument(
        "--load-data",
        action="store_true",
        help="Use LOAD DATA LOCAL INFILE instead of per-batch INSERT. "
             "Requires server-side local_infile=ON. Implies --insert.",
    )
    parser.add_argument(
        "--no-keep-chunks",
        action="store_true",
        help="In --load-data mode, delete each chunk file right after it loads. "
             "Caps peak disk use at one chunk. Useful on bastion hosts.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Rows per chunk file (default: 1000). Larger = fewer LOAD DATA "
             "statements but more peak disk use.",
    )
    args = parser.parse_args()

    if args.load_data:
        args.insert = True

    from src.config.app_config import load_dotenv_file, ConnectionConfig, AppPaths
    from src.db.connection import DatabaseManager
    from src.metadata.scanner import scan_database, save_scan_result

    load_dotenv_file(args.env_file)
    conn = ConnectionConfig.from_env()
    paths = AppPaths()
    paths.ensure_all()

    print(f"=== MySQL Data Factory {__version__} - Smoke Test ===\n")

    # 1. Connection
    print("[1] Testing connection...")
    db = DatabaseManager(config=conn)
    if not db.connect():
        print("[FAIL] Cannot connect to database")
        return 1
    tables = db.show_tables()
    print(f"  [OK] Connected, {len(tables)} tables found\n")

    # 2. Scan
    print("[2] Scanning metadata...")
    from src.metadata.scanner import scan_database, save_scan_result
    scan_result = scan_database(db)
    save_scan_result(scan_result, paths.metadata_cache_dir)
    print(f"  [OK] Scanned {len(scan_result.tables)} tables\n")

    # 3. Pick a table
    test_table = args.table
    if not test_table:
        # Find a table with data
        for name, meta in scan_result.tables.items():
            if meta.row_count > 0 and meta.primary_key_columns:
                test_table = name
                break

    if not test_table:
        print("[WARN] No suitable table with data found. Scan-only test passed.")
        db.disconnect()
        return 0

    meta = scan_result.tables[test_table]
    print(f"[3] Testing with table: {test_table}")
    print(f"    Rows: {meta.row_count}, PK: {meta.pk_display}\n")

    # 4. Generate preview
    print("[4] Generating preview...")
    from src.sample.selector import select_top_rows, normalize_sample_for_csv
    from src.generate.row_builder import generate_preview, resolve_start_values

    samples = select_top_rows(db, test_table, limit=1)
    if not samples:
        print(f"  [WARN] No data in {test_table}")
        db.disconnect()
        return 0

    sample = samples[0]
    template_row = normalize_sample_for_csv(sample.row_data)
    col_order = sample.column_order

    pk_cols = meta.primary_key_columns
    unique_cols = [c for c in meta.unique_key_columns if c not in pk_cols]

    start_values = resolve_start_values(db, test_table, template_row, pk_cols + unique_cols)
    db.disconnect()

    preview = generate_preview(
        template_fieldnames=col_order,
        template_row=template_row,
        pk_columns=pk_cols,
        unique_columns=unique_cols,
        start_values=start_values,
        count=args.rows,
    )

    print(f"  [OK] Generated {len(preview)} preview rows")
    for i, row in enumerate(preview[:3]):
        pk_val = row.get(pk_cols[0], "?") if pk_cols else "?"
        print(f"    Row {i+1}: PK={pk_val}")

    if len(preview) > 3:
        print(f"    ... ({len(preview) - 3} more)")

    # 5. Optional insert
    if args.insert and preview:
        import time as _time
        mode_label = "LOAD DATA LOCAL" if args.load_data else "INSERT"
        print(f"\n[5] Inserting {args.rows:,} rows into {test_table} (mode={mode_label})...")
        from src.generate.row_builder import generate_to_chunks
        from src.execute.batch_runner import insert_chunk_files, BatchConfig

        # Fast-mode probe: confirm server accepts LOAD DATA LOCAL before
        # we generate TSV. Falls back gracefully if not.
        effective_load_data = args.load_data
        if effective_load_data:
            probe = DatabaseManager(config=conn)
            if probe.connect():
                try:
                    if not probe.check_local_infile():
                        print("  [WARN] Server has local_infile=OFF; falling back to INSERT.")
                        effective_load_data = False
                finally:
                    probe.disconnect()

        output_dir = paths.output_dir / "smoke_test" / test_table
        file_format = "tsv" if effective_load_data else "csv"

        _gen_t0 = _time.monotonic()
        chunks = generate_to_chunks(
            template_fieldnames=col_order,
            template_row=template_row,
            pk_columns=pk_cols,
            unique_columns=unique_cols,
            start_values=start_values,
            total_rows=args.rows,
            chunk_size=args.chunk_size,
            output_dir=output_dir,
            file_format=file_format,
        )
        _gen_elapsed = _time.monotonic() - _gen_t0
        gen_rate = args.rows / _gen_elapsed if _gen_elapsed > 0 else 0
        print(f"  [OK] Generated {len(chunks)} chunks in {_gen_elapsed:.1f}s ({gen_rate:,.0f} rows/s)")

        _ins_t0 = _time.monotonic()
        report = insert_chunk_files(
            conn_config=conn,
            table_name=test_table,
            chunk_files=chunks,
            json_columns=meta.json_columns,
            batch_config=BatchConfig(
                batch_size=args.chunk_size,
                insert_mode="load_data" if effective_load_data else "insert",
                keep_chunks=not args.no_keep_chunks,
            ),
            campaign_id="smoke_test",
        )
        _ins_elapsed = _time.monotonic() - _ins_t0
        ins_rate = report.total_rows_inserted / _ins_elapsed if _ins_elapsed > 0 else 0

        report.save(paths.reports_dir)
        status = "OK" if report.status == "completed" else "FAIL"
        print(f"  [{status}] {report.total_rows_inserted:,}/{report.total_rows_attempted:,} inserted "
              f"in {_ins_elapsed:.1f}s ({ins_rate:,.0f} rows/s)")
        if report.error_summary:
            print(f"  [INFO] {report.error_summary}")
    else:
        print("\n[5] Skipping insert (use --insert to enable)")

    print("\n=== Smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())



