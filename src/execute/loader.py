"""
LOAD DATA LOCAL INFILE fast-insert path.

Used as an optional alternative to the per-row INSERT path in batch_runner.
Requires:
  - Server-side `local_infile = ON` (check via DatabaseManager.check_local_infile)
  - Client-side `local_infile=True` passed to pymysql.connect (set in connection.py)
  - TSV chunk files produced by row_builder._write_load_data_tsv

Throughput is typically ~5-10x of INSERT with executemany on a remote bastion link.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def build_load_data_sql(table_name: str, columns: list[str], abs_path: str) -> str:
    r"""
    Build a LOAD DATA LOCAL INFILE statement that matches the TSV layout
    produced by row_builder._write_load_data_tsv:
      - tab-separated
      - backslash-escaped (\t, \n, \r, \\)
      - no header row
      - explicit column list so TSV column order matches table column order
    """
    cols_sql = ", ".join(f"`{c}`" for c in columns)
    # MySQL accepts forward-slash paths on Windows clients; normalize to avoid
    # the single-quoted string accidentally eating a backslash.
    path_sql = abs_path.replace("\\", "/")
    return (
        f"LOAD DATA LOCAL INFILE '{path_sql}' "
        f"INTO TABLE `{table_name}` "
        f"CHARACTER SET utf8mb4 "
        r"FIELDS TERMINATED BY '\t' ESCAPED BY '\\' "
        r"LINES TERMINATED BY '\n' "
        f"({cols_sql})"
    )


def load_data_chunk(db, table_name: str, columns: list[str], tsv_path: Path) -> int:
    """
    Execute LOAD DATA LOCAL INFILE for one chunk file. Returns rows affected.

    MySQL-only. SQLite has no equivalent bulk-load statement, so callers
    targeting SQLite should stick with the INSERT executemany path.
    """
    # Hard guard: LOAD DATA LOCAL INFILE is MySQL-specific syntax. Reaching
    # this on any other dialect means a caller forgot to gate on is_mysql()
    # or fell through the campaign_runner probe — surface a clear error
    # rather than let the server complain about a syntax error.
    if hasattr(db, "is_mysql") and not db.is_mysql():
        raise RuntimeError(
            "LOAD DATA LOCAL INFILE is only supported on MySQL. "
            f"Current dialect: {getattr(db, 'dialect_name', 'unknown')!r}. "
            "Use insert_mode='insert' for non-MySQL targets."
        )
    abs_path = str(Path(tsv_path).resolve())
    sql = build_load_data_sql(table_name, columns, abs_path)
    logger.debug(f"LOAD DATA: {sql}")
    affected = db.execute(sql)
    return int(affected)
