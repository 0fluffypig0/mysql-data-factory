"""
Row generation engine.

Builds generated rows from a template + field strategies.
Handles chunked output to files for large datasets.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

import re as _re

from src.strategy.pk_planner import (
    increment_key_value, is_integer_like, analyze_pk_pattern, format_pk_value,
    PREFIX_NUM_RE,
)
from src.strategy.field_strategy import FieldStrategy


MAX_CHUNK_SIZE = 10000


def build_row(
    template_row: dict[str, str],
    pk_columns: list[str],
    unique_columns: list[str],
    start_values: dict[str, int | None],
    sequence_index: int,
    strategies: list[FieldStrategy] | None = None,
    marker_column: str = "",
    marker_value: str = "",
) -> dict[str, str]:
    """
    Build a single generated row from a template.

    Default behavior (no strategies): Only modify PK and unique key columns.
    With strategies: Apply each strategy.
    """
    row = dict(template_row)

    # If explicit strategies are provided, use them
    if strategies:
        strategy_map = {s.column_name: s for s in strategies}
        for col, strategy in strategy_map.items():
            if col not in row:
                continue
            if strategy.strategy_type == "pk_increment":
                row[col] = increment_key_value(
                    template_row.get(col), sequence_index, start_values.get(col))
            elif strategy.strategy_type == "unique_increment":
                row[col] = increment_key_value(
                    template_row.get(col), sequence_index, start_values.get(col))
            elif strategy.strategy_type == "time_offset":
                mode = strategy.params.get("mode", "now")
                if mode == "now":
                    row[col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif strategy.strategy_type == "marker":
                row[col] = strategy.params.get("value", marker_value)
            elif strategy.strategy_type == "db_default":
                row[col] = ""  # Let DB handle it
            # "copy" and "sample_choice" keep template value
    else:
        # Legacy mode: only modify PK and unique columns
        for col in pk_columns:
            row[col] = increment_key_value(
                template_row.get(col), sequence_index, start_values.get(col))
        for col in unique_columns:
            row[col] = increment_key_value(
                template_row.get(col), sequence_index, start_values.get(col))

    # Apply marker if specified and no strategy handled it
    if marker_column and marker_value and marker_column in row:
        if not strategies or not any(s.column_name == marker_column and s.strategy_type == "marker" for s in (strategies or [])):
            row[marker_column] = marker_value

    return row


def resolve_start_values(
    db,
    table_name: str | None,
    template_row: dict[str, str],
    key_columns: list[str],
) -> dict[str, int | None]:
    """
    Calculate starting values for PK/unique key columns.

    For integer columns: max(column) + 1
    For string columns: count existing prefix matches + 1
    """
    from src.strategy.pk_planner import is_integer_like

    start_values: dict[str, int | None] = {}

    for column in key_columns:
        template_value = template_row.get(column)
        start_values[column] = None

        if not is_integer_like(template_value):
            if db is None or not table_name:
                continue

            str_val = str(template_value) if template_value is not None else ""

            # If value matches prefix+number pattern (e.g. "SEED_t_pub_lo_0001", "KC0007"),
            # count ALL rows sharing the same prefix so we start after the existing maximum.
            qt = db.quote_identifier(table_name)
            qc = db.quote_identifier(column)

            # Use '!' as the LIKE escape char instead of backslash so the same
            # query works on both MySQL (which would interpret '\\' in SQL
            # string literals) and SQLite (which requires a 1-char ESCAPE
            # arg). '!' is not a SQL-level escape on either engine.
            ESC = "!"

            def _esc_like(s: str) -> str:
                return (s.replace(ESC, ESC + ESC)
                         .replace("%", ESC + "%")
                         .replace("_", ESC + "_"))

            m = PREFIX_NUM_RE.match(str_val)
            if m:
                prefix = m.group(1)
                like_pattern = f"{_esc_like(prefix)}%"
                rows = db.query(
                    f"SELECT COUNT(*) FROM {qt} WHERE {qc} LIKE %s ESCAPE '{ESC}'",
                    (like_pattern,),
                )
                count = int(rows[0][0]) if rows else 0
                start_values[column] = count + 1
            else:
                # Non-prefix+number string: look for variants appended with _<suffix>
                like_pattern = f"{_esc_like(str_val)}{ESC}_%"
                rows = db.query(
                    f"SELECT COUNT(*) FROM {qt} "
                    f"WHERE {qc} = %s OR {qc} LIKE %s ESCAPE '{ESC}'",
                    (str_val, like_pattern),
                )
                count = int(rows[0][0]) if rows else 0
                start_values[column] = max(count, 1)
            continue

        if db is None or not table_name:
            continue

        max_val = db.get_max_pk_value(table_name, column)
        if max_val is not None and is_integer_like(max_val):
            start_values[column] = int(str(max_val)) + 1

    return start_values


def generate_to_chunks(
    template_fieldnames: list[str],
    template_row: dict[str, str],
    pk_columns: list[str],
    unique_columns: list[str],
    start_values: dict[str, int | None],
    total_rows: int,
    chunk_size: int,
    output_dir: Path,
    strategies: list[FieldStrategy] | None = None,
    marker_column: str = "",
    marker_value: str = "",
    progress_callback=None,
    pk_columns_for_filename: list[str] | None = None,
    file_format: str = "csv",
) -> list[Path]:
    """
    Generate rows in chunks and write to CSV or TSV files.

    pk_columns_for_filename: if provided, first column is used to embed PK range in chunk filenames.
    file_format: "csv" (default, for INSERT path) or "tsv" (MySQL-native LOAD DATA format).
    Returns list of generated chunk file paths.
    """
    chunk_size = min(chunk_size, MAX_CHUNK_SIZE)
    if chunk_size <= 0:
        chunk_size = 1000

    # The key column for embedding range in the filename
    _pk_name_col = (pk_columns_for_filename or pk_columns or [None])[0]

    fmt = (file_format or "csv").lower()
    if fmt not in ("csv", "tsv"):
        fmt = "csv"
    ext = "tsv" if fmt == "tsv" else "csv"

    output_dir.mkdir(parents=True, exist_ok=True)
    total_chunks = math.ceil(total_rows / chunk_size)
    generated_total = 0
    global_index = 0
    chunk_files: list[Path] = []

    for chunk_idx in range(1, total_chunks + 1):
        remaining = total_rows - generated_total
        current_count = min(chunk_size, remaining)
        rows: list[dict[str, str]] = []

        for _ in range(current_count):
            row = build_row(
                template_row, pk_columns, unique_columns,
                start_values, global_index, strategies,
                marker_column, marker_value,
            )
            rows.append(row)
            generated_total += 1
            global_index += 1

        # Build chunk filename with optional PK range
        if _pk_name_col and rows:
            pk_first = _safe_pk_token(rows[0].get(_pk_name_col, ""))
            pk_last = _safe_pk_token(rows[-1].get(_pk_name_col, ""))
            chunk_name = f"chunk_{chunk_idx:06d}__rows_{current_count}__range_{pk_first}__{pk_last}.{ext}"
        else:
            chunk_name = f"chunk_{chunk_idx:06d}.{ext}"

        chunk_path = output_dir / chunk_name
        if fmt == "tsv":
            _write_load_data_tsv(chunk_path, template_fieldnames, rows)
        else:
            _write_csv(chunk_path, template_fieldnames, rows)
        chunk_files.append(chunk_path)

        if progress_callback:
            progress_callback(chunk_idx, total_chunks, current_count, generated_total)

        logger.info(f"Chunk {chunk_idx}/{total_chunks}: {chunk_path.name} ({current_count} rows)")

    logger.success(f"Generated {generated_total} rows in {total_chunks} chunks (format={fmt})")
    return chunk_files


def generate_preview(
    template_fieldnames: list[str],
    template_row: dict[str, str],
    pk_columns: list[str],
    unique_columns: list[str],
    start_values: dict[str, int | None],
    count: int = 5,
    strategies: list[FieldStrategy] | None = None,
    marker_column: str = "",
    marker_value: str = "",
) -> list[dict[str, str]]:
    """Generate a small preview of rows without writing to disk."""
    rows = []
    for i in range(count):
        row = build_row(
            template_row, pk_columns, unique_columns,
            start_values, i, strategies, marker_column, marker_value,
        )
        rows.append(row)
    return rows


def _safe_pk_token(val: str, max_len: int = 12) -> str:
    """Sanitize a PK value for use in a filename, with length protection."""
    sanitized = _re.sub(r'[^A-Za-z0-9_]', '_', str(val))
    if len(sanitized) <= max_len:
        return sanitized
    # Keep first (max_len-5) chars + last 4 chars, joined with "~"
    return sanitized[: max_len - 5] + "~" + sanitized[-4:]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _escape_tsv_value(value: Any) -> str:
    r"""
    Encode a single cell for MySQL-native TSV (LOAD DATA LOCAL INFILE).

    Rules:
    - None or empty string -> \N  (SQL NULL literal under unquoted fields)
    - Escape backslash, tab, newline, carriage return
    - No surrounding quotes (MySQL default tab-terminated format)
    """
    if value is None:
        return "\\N"
    s = str(value)
    if s == "":
        return "\\N"
    # Order matters: backslash first so we don't double-escape our own escapes
    s = s.replace("\\", "\\\\")
    s = s.replace("\t", "\\t")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    return s


def _write_load_data_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    r"""
    Write rows in MySQL-native TSV format for LOAD DATA LOCAL INFILE.

    Format:
      - No header row (LOAD DATA expects raw data)
      - Tab-separated fields
      - \N marks NULL (also used when source value is empty string,
        matching INSERT path's _normalize_value behavior)
      - \\ \t \n \r escape sequences
      - utf-8 encoding (no BOM — MySQL cannot strip a UTF-8 BOM automatically)
      - LF line endings
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        for row in rows:
            cells = [_escape_tsv_value(row.get(col, "")) for col in fieldnames]
            f.write("\t".join(cells))
            f.write("\n")
