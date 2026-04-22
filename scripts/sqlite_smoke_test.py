#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 - SQLite Smoke Test

Creates a fresh SQLite database in a temp directory, seeds it with a
small schema + sample rows, then exercises the same pipeline the MySQL
smoke test uses: scan metadata → pick template row → generate rows →
INSERT via the batch runner.

This proves the multi-dialect abstraction end-to-end without needing
an external MySQL server, and it is the primary regression test for
SQLite users.

Usage:
    python scripts/sqlite_smoke_test.py [--keep] [--rows 50]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"SQLite smoke test for MySQL Data Factory {__version__}"
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=20,
        help="Number of rows to generate/insert (default: 20).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="Rows per chunk file (default: 10).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temp directory (and the SQLite file) after the test "
             "for inspection. Default: cleaned up on exit.",
    )
    args = parser.parse_args()

    from src.config.app_config import ConnectionConfig, AppPaths
    from src.db.connection import DatabaseManager
    from src.metadata.scanner import scan_database, save_scan_result
    from src.sample.selector import select_top_rows, normalize_sample_for_csv
    from src.generate.row_builder import (
        generate_preview, generate_to_chunks, resolve_start_values,
    )
    from src.execute.batch_runner import insert_chunk_files, BatchConfig

    print(f"=== MySQL Data Factory {__version__} - SQLite Smoke Test ===\n")

    # 1. Create temp workspace with a fresh SQLite DB
    tmp_dir = Path(tempfile.mkdtemp(prefix="mdf_sqlite_"))
    db_path = tmp_dir / "smoke.sqlite3"
    print(f"[1] Temp workspace: {tmp_dir}")

    try:
        conn = ConnectionConfig(dialect="sqlite", database=str(db_path))
        paths = AppPaths(root=tmp_dir)
        paths.ensure_all()

        # 2. Seed schema + sample rows
        print("[2] Seeding schema and sample rows...")
        db = DatabaseManager(config=conn)
        if not db.connect():
            print("[FAIL] Cannot open SQLite DB")
            return 1
        db.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        db.executemany(
            "INSERT INTO users (id, username, email, status) VALUES (?, ?, ?, ?)",
            [
                (1, "alice", "alice@example.com", "active"),
                (2, "bob",   "bob@example.com",   "active"),
                (3, "carol", "carol@example.com", "suspended"),
            ],
        )
        print(f"  [OK] Seeded 3 rows into users (max id: {db.get_max_pk_value('users', 'id')})")

        # 3. Scan metadata
        print("[3] Scanning metadata...")
        scan_result = scan_database(db)
        save_scan_result(scan_result, paths.metadata_cache_dir)
        print(f"  [OK] Scanned {len(scan_result.tables)} tables")

        meta = scan_result.tables["users"]
        print(f"  users: {meta.row_count} rows, PK: {meta.pk_display}")

        # 4. Generate preview
        print("[4] Generating preview...")
        samples = select_top_rows(db, "users", limit=1)
        assert samples, "no sample row?"
        sample = samples[0]
        template_row = normalize_sample_for_csv(sample.row_data)
        col_order = sample.column_order

        pk_cols = meta.primary_key_columns
        unique_cols = [c for c in meta.unique_key_columns if c not in pk_cols]
        start_values = resolve_start_values(db, "users", template_row, pk_cols + unique_cols)
        db.disconnect()

        preview = generate_preview(
            template_fieldnames=col_order,
            template_row=template_row,
            pk_columns=pk_cols,
            unique_columns=unique_cols,
            start_values=start_values,
            count=min(3, args.rows),
        )
        print(f"  [OK] Generated {len(preview)} preview rows")
        for i, row in enumerate(preview):
            pk_val = row.get(pk_cols[0], "?") if pk_cols else "?"
            u_val = row.get("username", "?")
            print(f"    Row {i+1}: id={pk_val}, username={u_val}")

        # 5. Generate chunks + insert
        print(f"\n[5] Generating + inserting {args.rows} rows via INSERT path...")
        output_dir = paths.output_dir / "sqlite_smoke" / "users"
        chunks = generate_to_chunks(
            template_fieldnames=col_order,
            template_row=template_row,
            pk_columns=pk_cols,
            unique_columns=unique_cols,
            start_values=start_values,
            total_rows=args.rows,
            chunk_size=args.chunk_size,
            output_dir=output_dir,
            file_format="csv",  # SQLite always uses INSERT path
        )
        print(f"  [OK] Generated {len(chunks)} chunks")

        report = insert_chunk_files(
            conn_config=conn,
            table_name="users",
            chunk_files=chunks,
            json_columns=meta.json_columns,
            batch_config=BatchConfig(
                batch_size=args.chunk_size,
                insert_mode="insert",
            ),
            campaign_id="sqlite_smoke",
        )
        report.save(paths.reports_dir)

        status = "OK" if report.status == "completed" else "FAIL"
        print(f"  [{status}] {report.total_rows_inserted}/{report.total_rows_attempted} inserted")
        if report.error_summary:
            print(f"  [INFO] {report.error_summary}")

        # 6. Verify the rows landed
        print("\n[6] Verifying inserted rows...")
        db2 = DatabaseManager(config=conn)
        db2.connect()
        total = db2.count_rows("users")
        max_id = db2.get_max_pk_value("users", "id")
        print(f"  users now has {total} rows, max id={max_id}")
        expected_total = 3 + args.rows  # seeded + generated
        if total != expected_total:
            print(f"  [FAIL] Expected {expected_total} rows, got {total}")
            db2.disconnect()
            return 1
        db2.disconnect()

        # 7. Test LOAD DATA fallback — should silently use INSERT on SQLite
        print("\n[7] Checking LOAD DATA fallback on SQLite (expected: warn + use INSERT)...")
        fallback_chunks = generate_to_chunks(
            template_fieldnames=col_order,
            template_row=template_row,
            pk_columns=pk_cols,
            unique_columns=unique_cols,
            start_values={k: (v or 0) + args.rows for k, v in start_values.items()},
            total_rows=5,
            chunk_size=5,
            output_dir=output_dir / "fallback",
            file_format="csv",
        )
        fallback_report = insert_chunk_files(
            conn_config=conn,
            table_name="users",
            chunk_files=fallback_chunks,
            batch_config=BatchConfig(batch_size=5, insert_mode="load_data"),
            campaign_id="sqlite_smoke_fallback",
        )
        if fallback_report.status == "completed" and fallback_report.total_rows_inserted == 5:
            print("  [OK] Fallback works — 5 rows inserted via INSERT despite load_data request")
        else:
            print(f"  [FAIL] Fallback report: {fallback_report.status}, "
                  f"{fallback_report.total_rows_inserted}/{fallback_report.total_rows_attempted}")
            return 1

        print("\n=== SQLite smoke test complete: OK ===")
        return 0

    finally:
        if args.keep:
            print(f"\n[keep] Temp workspace preserved at: {tmp_dir}")
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
