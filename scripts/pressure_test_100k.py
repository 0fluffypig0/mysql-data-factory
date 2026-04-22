#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 - 100k Pressure Test

Measures end-to-end throughput for 100,000 row insertion:
- Generate phase timing
- Insert phase timing (with shared connection, simulating bastion scenario)
- Batch-level stats
- Recommendations for 1M rows

Usage:
    python scripts/pressure_test_100k.py [--env-file .env] [--table TABLE] [--rows 100000]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import __version__


def fmt_seconds(secs: float) -> str:
    if secs < 60:
        return f"{secs:.2f}s"
    return f"{int(secs//60)}m{secs%60:.1f}s"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"MySQL Data Factory {__version__} - 100k pressure test "
                    "(throughput and latency benchmark)"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with DB credentials (default: .env in project root)",
    )
    parser.add_argument(
        "--table",
        help="Target table. If omitted, auto-picks the first table with data and a primary key.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=100_000,
        help="Number of rows to insert (default: 100000). "
             "Script extrapolates 1M-row ETA from the measured throughput.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per INSERT batch (default: 500). "
             "Try 1000-2000 for higher throughput; too large may exceed max_allowed_packet.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Rows per generated CSV chunk file (default: 5000). "
             "Larger chunks mean fewer files but higher peak memory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate CSV chunks but skip the insert phase. Useful for I/O profiling.",
    )
    args = parser.parse_args()

    from src.config.app_config import load_dotenv_file, ConnectionConfig, AppPaths
    from src.db.connection import DatabaseManager
    from src.metadata.scanner import scan_database
    from src.sample.selector import select_top_rows, normalize_sample_for_csv
    from src.generate.row_builder import generate_to_chunks, resolve_start_values
    from src.execute.batch_runner import insert_chunk_files, BatchConfig

    load_dotenv_file(args.env_file)
    conn = ConnectionConfig.from_env()
    paths = AppPaths()
    paths.ensure_all()

    print(f"=== MySQL Data Factory {__version__} - Pressure Test ({args.rows:,} rows) ===")
    print(f"    batch_size={args.batch_size}  chunk_size={args.chunk_size}  dry_run={args.dry_run}\n")

    # ── 1. Connect (shared, simulating bastion keep-alive) ──
    t0 = time.perf_counter()
    db = DatabaseManager(config=conn)
    if not db.connect():
        print("[FAIL] Cannot connect")
        return 1
    t_connect = time.perf_counter() - t0
    print(f"[1] Connected in {fmt_seconds(t_connect)}")

    # ── 2. Scan & pick table (use cache if available) ──
    t1 = time.perf_counter()
    from src.metadata.scanner import load_scan_result, save_scan_result
    scan_result = load_scan_result(paths.metadata_cache_dir, conn.database)
    if scan_result is None:
        scan_result = scan_database(db)
        save_scan_result(scan_result, paths.metadata_cache_dir)
        print(f"[2] Scanned {len(scan_result.tables)} tables in {fmt_seconds(time.perf_counter() - t1)} (fresh scan)")
    else:
        print(f"[2] Loaded {len(scan_result.tables)} tables from cache in {fmt_seconds(time.perf_counter() - t1)}")
    t_scan = time.perf_counter() - t1

    test_table = args.table
    if not test_table:
        for name, meta in scan_result.tables.items():
            if meta.row_count > 0 and meta.primary_key_columns:
                test_table = name
                break
    if not test_table:
        print("[FAIL] No suitable table found")
        return 1

    meta = scan_result.tables[test_table]
    pk_cols = meta.primary_key_columns or []
    unique_cols = [c for c in meta.unique_key_columns if c not in pk_cols]
    json_cols = meta.json_columns or []
    print(f"[3] Target table: {test_table}  (existing rows: {meta.row_count:,}, PK: {pk_cols})\n")
    # ── 3. Sample ──
    t2 = time.perf_counter()
    samples = select_top_rows(db, test_table, limit=1)
    if not samples:
        print("[FAIL] No rows in table to use as template")
        return 1
    sample = samples[0]
    template_row = normalize_sample_for_csv(sample.row_data)
    col_order = sample.column_order or list(template_row.keys())
    t_sample = time.perf_counter() - t2
    print(f"[4] Sample fetched in {fmt_seconds(t_sample)}")

    # ── 4. Resolve start values ──
    t3 = time.perf_counter()
    start_values = resolve_start_values(db, test_table, template_row, pk_cols + unique_cols)
    t_resolve = time.perf_counter() - t3
    print(f"[5] Start values resolved in {fmt_seconds(t_resolve)}: {start_values}")

    # ── 5. Generate chunks ──
    output_dir = paths.output_dir / "pressure_test" / test_table
    t4 = time.perf_counter()
    chunk_files = generate_to_chunks(
        template_fieldnames=col_order,
        template_row=template_row,
        pk_columns=pk_cols,
        unique_columns=unique_cols,
        start_values=start_values,
        total_rows=args.rows,
        chunk_size=args.chunk_size,
        output_dir=output_dir,
    )
    t_generate = time.perf_counter() - t4
    total_chunk_bytes = sum(f.stat().st_size for f in chunk_files)
    print(f"[6] Generated {len(chunk_files)} chunk(s), {total_chunk_bytes/1024/1024:.1f} MB in {fmt_seconds(t_generate)}")
    print(f"    Generate throughput: {args.rows / t_generate:,.0f} rows/s")

    if args.dry_run:
        print("\n[DRY-RUN] Skipping insert phase.")
        db.disconnect()
        return 0

    # ── 6. Insert using shared connection (bastion pattern) ──
    print(f"\n[7] Inserting {args.rows:,} rows (shared connection, batch_size={args.batch_size})...")
    t5 = time.perf_counter()
    report = insert_chunk_files(
        conn_config=conn,
        table_name=test_table,
        chunk_files=chunk_files,
        json_columns=json_cols,
        batch_config=BatchConfig(
            batch_size=args.batch_size,
            dry_run=False,
            stop_on_error=False,
            throttle_ms=0,
        ),
        campaign_id="pressure_test",
        task_id="pt_100k",
        db=db,  # shared connection — bastion safe
    )
    t_insert = time.perf_counter() - t5
    t_total = time.perf_counter() - t0

    db.disconnect()

    # ── 7. Report ──
    print()
    print("=" * 55)
    print("  PRESSURE TEST RESULTS")
    print("=" * 55)
    print(f"  Table            : {test_table}")
    print(f"  Rows attempted   : {report.total_rows_attempted:>10,}")
    print(f"  Rows inserted    : {report.total_rows_inserted:>10,}")
    print(f"  Failed batches   : {report.failed_batches:>10,}")
    print(f"  Status           : {report.status}")
    print(f"  PK range         : {report.pk_range_start} ~ {report.pk_range_end}")
    print()
    print(f"  Generate time    : {fmt_seconds(t_generate):>10}  ({args.rows/t_generate:,.0f} rows/s)")
    print(f"  Insert time      : {fmt_seconds(t_insert):>10}  ({report.total_rows_inserted/t_insert if t_insert>0 else 0:,.0f} rows/s)")
    print(f"  Total time       : {fmt_seconds(t_total):>10}")
    print(f"  Batches          : {report.total_batches:>10,}  (size={args.batch_size})")
    print(f"  Chunks           : {len(chunk_files):>10,}  (size={args.chunk_size})")
    print()

    # ── 8. Extrapolated 1M estimate ──
    scale = 1_000_000 / args.rows
    est_gen = t_generate * scale
    est_ins = t_insert * scale
    est_total = est_gen + est_ins
    print("  EXTRAPOLATED 1M ROW ESTIMATE")
    print(f"  Generate         : ~{fmt_seconds(est_gen)}")
    print(f"  Insert           : ~{fmt_seconds(est_ins)}")
    print(f"  Total            : ~{fmt_seconds(est_total)}")
    print()
    print("  RECOMMENDATION")
    ins_rate = report.total_rows_inserted / t_insert if t_insert > 0 else 0
    if ins_rate >= 5000:
        print("  Current batch_size is efficient. For 1M rows, increase")
        print("  chunk_size to 10000 and batch_size to 1000 to reduce")
        print("  loop overhead. Expected total time: ~" + fmt_seconds(est_total))
    elif ins_rate >= 2000:
        print("  Moderate throughput. Consider increasing batch_size to")
        print("  1000-2000 and chunk_size to 10000 for 1M row runs.")
    else:
        print("  Low throughput — check network latency or MySQL load.")
        print("  For 1M rows, split into multiple campaigns or add")
        print("  throttle_ms=0 and increase batch_size.")
    print("=" * 55)

    report.save(paths.reports_dir)
    print(f"\nReport saved to: {paths.reports_dir}")
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())


