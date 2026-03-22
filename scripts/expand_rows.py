#!/usr/bin/env python3
"""Expand one template CSV into generated rows for a single table insert flow."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
INTEGER_RE = re.compile(r"^-?\d+$")


def resolve_env_file(env_file: str) -> Path:
    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path
    return env_path


def maybe_load_dotenv(env_file: str) -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv(resolve_env_file(env_file), override=True)


def parse_column_list(raw_value: Optional[str]) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def is_integer_like(value: object) -> bool:
    return value is not None and INTEGER_RE.match(str(value).strip()) is not None


def format_integer_like(value: int, template_value: object) -> str:
    raw = "" if template_value is None else str(template_value).strip()
    if raw.startswith("-"):
        width = len(raw) - 1
        return f"-{abs(value):0{width}d}" if width > 1 and raw[1:].startswith("0") else str(value)
    if len(raw) > 1 and raw.startswith("0"):
        return str(value).zfill(len(raw))
    return str(value)


def increment_key_value(
    template_value: object,
    index: int,
    start_override: Optional[int],
    fallback_label: str,
) -> object:
    raw = "" if template_value is None else str(template_value)
    if raw == "":
        return raw
    if start_override is not None:
        return format_integer_like(start_override + index, template_value)
    if is_integer_like(raw):
        return format_integer_like(int(raw) + index, template_value)
    return f"{raw}_{index + 1:06d}"


def shift_time_value(value: object, index: int, days: int, seconds: int) -> object:
    import pandas as pd

    raw = "" if value is None else str(value).strip()
    if raw == "" or (days == 0 and seconds == 0):
        return raw

    timestamp = pd.to_datetime(raw, errors="coerce")
    if pd.isna(timestamp):
        return raw

    shifted = timestamp + pd.Timedelta(days=days * index, seconds=seconds * index)
    if ":" in raw:
        return shifted.strftime("%Y-%m-%d %H:%M:%S")
    return shifted.strftime("%Y-%m-%d")


def query_max_value(db, table_name: str, column_name: str) -> Optional[int]:
    rows = db.query(f"SELECT MAX(`{column_name}`) FROM `{table_name}`")
    if not rows:
        return None
    max_value = rows[0][0]
    if max_value is None:
        return None
    if is_integer_like(max_value):
        return int(str(max_value))
    return None


def resolve_numeric_starts(
    db,
    table_name: Optional[str],
    key_columns: list[str],
    template_rows: list[dict[str, object]],
) -> dict[str, Optional[int]]:
    starts: dict[str, Optional[int]] = {}
    first_row = template_rows[0]
    for column in key_columns:
        value = first_row.get(column)
        starts[column] = None
        if not is_integer_like(value):
            continue
        if db is None or table_name is None:
            continue
        try:
            max_value = query_max_value(db, table_name, column)
            if max_value is not None:
                starts[column] = max_value + 1
        except Exception:
            starts[column] = None
    return starts


def parse_args() -> argparse.Namespace:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()
    maybe_load_dotenv(env_args.env_file)

    parser = argparse.ArgumentParser(description="Expand a template CSV into generated rows.")
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--pk-cols", default=os.getenv("PRIMARY_KEY_COLUMNS"))
    parser.add_argument("--unique-cols", default=os.getenv("UNIQUE_KEY_COLUMNS"))
    parser.add_argument("--time-cols", default=os.getenv("TIME_OFFSET_COLUMNS"))
    parser.add_argument("--json-cols", default=os.getenv("JSON_COLUMNS"))
    parser.add_argument(
        "--time-offset-days",
        type=int,
        default=int(os.getenv("TIME_OFFSET_DAYS", "0")),
    )
    parser.add_argument(
        "--time-offset-seconds",
        type=int,
        default=int(os.getenv("TIME_OFFSET_SECONDS", "0")),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import pandas as pd

    if args.rows <= 0:
        print("[ERROR] --rows must be greater than 0.")
        return 1

    table_name = args.table
    if table_name and not TABLE_NAME_RE.match(table_name):
        print("[ERROR] Table name may only contain letters, numbers, and underscores.")
        return 1

    pk_columns = parse_column_list(args.pk_cols)
    unique_columns = [col for col in parse_column_list(args.unique_cols) if col not in pk_columns]
    time_columns = parse_column_list(args.time_cols)
    json_columns = parse_column_list(args.json_cols)
    if not pk_columns:
        print("[ERROR] PRIMARY_KEY_COLUMNS is required for expand_rows.py.")
        return 1

    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))
    input_path = Path(args.input) if args.input else csv_base_dir / (table_name or "table") / "template.csv"
    output_path = Path(args.output) if args.output else csv_base_dir / (table_name or "table") / "generated.csv"

    if not input_path.exists():
        print(f"[ERROR] Template CSV not found: {input_path}")
        return 1

    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    if df.empty:
        print("[ERROR] Template CSV is empty.")
        return 1

    expected_columns = pk_columns + unique_columns + time_columns + json_columns
    missing_columns = [column for column in expected_columns if column not in df.columns]
    if missing_columns:
        print(f"[ERROR] Configured columns not found in CSV: {missing_columns}")
        return 1

    template_rows = df.to_dict(orient="records")
    db = None
    if table_name:
        from src.database import DatabaseManager

        probe_db = DatabaseManager()
        if probe_db.connect():
            db = probe_db

    try:
        numeric_starts = resolve_numeric_starts(db, table_name, pk_columns + unique_columns, template_rows)
        first_row = template_rows[0]
        generated_rows: list[dict[str, object]] = []

        for index in range(args.rows):
            base_row = template_rows[index % len(template_rows)].copy()

            for column in pk_columns:
                base_row[column] = increment_key_value(
                    first_row.get(column),
                    index,
                    numeric_starts.get(column),
                    column,
                )

            for column in unique_columns:
                base_row[column] = increment_key_value(
                    first_row.get(column),
                    index,
                    numeric_starts.get(column),
                    column,
                )

            for column in time_columns:
                base_row[column] = shift_time_value(
                    base_row.get(column),
                    index,
                    args.time_offset_days,
                    args.time_offset_seconds,
                )

            generated_rows.append(base_row)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(generated_rows, columns=df.columns).to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )

        print(f"[OK] Generated {len(generated_rows)} rows.")
        print(f"Output: {output_path}")
        print(f"Primary key columns: {pk_columns}")
        print(f"Unique key columns: {unique_columns}")
        print(f"Time offset columns: {time_columns}")
        print(f"JSON columns: {json_columns}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Expansion failed: {exc}")
        return 1
    finally:
        if db is not None:
            db.disconnect()


if __name__ == "__main__":
    sys.exit(main())
