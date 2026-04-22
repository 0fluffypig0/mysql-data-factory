"""
Dry-run estimator for campaign plans.

Predicts, without touching target tables:
  - Total rows to be generated
  - CSV chunk-file footprint on disk (total + peak single chunk)
  - Estimated insert time
  - Free disk space on the chunk output partition

The row-byte estimate is derived by serializing a sampled template row to CSV
(same dialect as `generate_to_chunks`) and multiplying by row_count. This keeps
the estimator in sync with what actually gets written at runtime.
"""

from __future__ import annotations

import csv
import io
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from src.config.app_config import ConnectionConfig
from src.db.connection import DatabaseManager
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan
from src.sample.selector import normalize_sample_for_csv, select_by_pk, select_top_rows


# Rough default insert rate (rows/sec). Tune via `insert_rate` parameter if
# you know your environment is faster or slower.
DEFAULT_INSERT_RATE_ROWS_PER_SEC = 8000


@dataclass
class TaskEstimate:
    table_name: str
    row_count: int
    avg_bytes_per_row: int = 0
    total_csv_bytes: int = 0
    chunks: int = 0
    peak_chunk_bytes: int = 0
    seconds_est: float = 0.0
    sample_ok: bool = False
    error: str = ""


@dataclass
class CampaignEstimate:
    tasks: list[TaskEstimate] = field(default_factory=list)
    total_rows: int = 0
    total_csv_bytes: int = 0
    peak_chunk_bytes: int = 0
    total_seconds_est: float = 0.0
    disk_free_bytes: int = 0
    disk_total_bytes: int = 0
    disk_check_path: str = ""
    insert_rate: int = DEFAULT_INSERT_RATE_ROWS_PER_SEC

    @property
    def disk_ok(self) -> bool:
        return self.disk_total_bytes > 0 and self.total_csv_bytes < self.disk_free_bytes

    @property
    def disk_warn(self) -> bool:
        # Will consume >=80% of free space.
        return (self.disk_total_bytes > 0
                and self.total_csv_bytes >= self.disk_free_bytes * 0.8)


def _csv_bytes_for_row(row: dict) -> int:
    """Serialize a single row dict as a CSV line; return its UTF-8 byte length."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow([str(v) if v is not None else "" for v in row.values()])
    return len(buf.getvalue().encode("utf-8"))


def _probe_disk(path: Path) -> tuple[int, int, str]:
    """Return (free, total, resolved_path) for the first existing ancestor of path."""
    p: Path | None = path
    while p is not None and not p.exists():
        parent = p.parent
        if parent == p:
            p = None
            break
        p = parent
    if p is None or not p.exists():
        return (0, 0, str(path))
    try:
        usage = shutil.disk_usage(str(p))
        return (usage.free, usage.total, str(p))
    except Exception:
        return (0, 0, str(p))


def estimate_campaign(
    plan: CampaignPlan,
    conn_config: ConnectionConfig,
    scan_result: DatabaseScanResult | None,
    output_dir: Path,
    insert_rate: int = DEFAULT_INSERT_RATE_ROWS_PER_SEC,
    db: DatabaseManager | None = None,
) -> CampaignEstimate:
    """
    Produce a dry-run estimate for every task in `plan`.

    If `db` is supplied, it is reused (and not disconnected). Otherwise, a
    fresh connection is opened and closed inside this function.

    On DB connection failure, per-table byte estimates are skipped but disk
    info is still populated, so the caller can at least show free space.
    """
    est = CampaignEstimate(insert_rate=insert_rate)
    free, total, resolved = _probe_disk(output_dir)
    est.disk_free_bytes = free
    est.disk_total_bytes = total
    est.disk_check_path = resolved

    owns_db = False
    if db is None:
        db = DatabaseManager(config=conn_config)
        if not db.connect():
            for task in plan.tasks:
                te = TaskEstimate(
                    table_name=task.table_name,
                    row_count=task.row_count,
                    error="DB connection failed",
                )
                est.tasks.append(te)
                est.total_rows += task.row_count
            return est
        owns_db = True

    try:
        for task in plan.tasks:
            te = TaskEstimate(table_name=task.table_name, row_count=task.row_count)
            meta = scan_result.tables.get(task.table_name) if scan_result else None
            try:
                pk_cols = meta.primary_key_columns if meta else []
                sample = None
                if task.sample_pk_value and pk_cols:
                    sample = select_by_pk(db, task.table_name, pk_cols, [task.sample_pk_value])
                if sample is None:
                    results = select_top_rows(db, task.table_name, limit=1)
                    sample = results[0] if results else None

                if sample is None:
                    te.error = "No sample row available"
                else:
                    tmpl = normalize_sample_for_csv(sample.row_data)
                    bpr = _csv_bytes_for_row(tmpl)
                    te.avg_bytes_per_row = bpr
                    te.total_csv_bytes = bpr * task.row_count
                    batch = max(1, task.batch_size)
                    te.chunks = max(1, (task.row_count + batch - 1) // batch)
                    te.peak_chunk_bytes = bpr * min(task.row_count, batch)
                    te.seconds_est = (task.row_count / insert_rate) if insert_rate > 0 else 0.0
                    te.sample_ok = True
            except Exception as exc:
                te.error = str(exc)

            est.tasks.append(te)
            est.total_rows += task.row_count
            est.total_csv_bytes += te.total_csv_bytes
            est.peak_chunk_bytes = max(est.peak_chunk_bytes, te.peak_chunk_bytes)
            est.total_seconds_est += te.seconds_est
    finally:
        if owns_db:
            db.disconnect()

    return est
