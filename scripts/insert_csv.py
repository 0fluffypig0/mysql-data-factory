#!/usr/bin/env python3
"""Dry-run check and batch insert a generated CSV into one target table."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def parse_column_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run check or insert a generated CSV.")
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))
    parser.add_argument("--input")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("INSERT_BATCH_SIZE", "500")),
    )
    parser.add_argument("--pk-cols", default=os.getenv("PRIMARY_KEY_COLUMNS"))
    parser.add_argument("--json-cols", default=os.getenv("JSON_COLUMNS"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-db-check",
        action="store_true",
        help="Allow dry-run validation without connecting to MySQL or checking table schema.",
    )
    return parser.parse_args()


def count_empty_pk_rows(df, pk_columns: list[str]) -> int:
    import pandas as pd

    if not pk_columns:
        return 0
    return int((df[pk_columns].replace("", pd.NA).isna().any(axis=1)).sum())


def count_duplicate_pk_rows(df, pk_columns: list[str]) -> int:
    if not pk_columns:
        return 0
    return int(df.duplicated(subset=pk_columns).sum())


def detect_json_columns(table_description: list[tuple]) -> list[str]:
    return [str(column[0]) for column in table_description if len(column) > 1 and "json" in str(column[1]).lower()]


def normalize_json_value(raw_value: object) -> tuple[bool, str, str | None]:
    raw = "" if raw_value is None else str(raw_value)
    if raw.strip() == "":
        return True, "", None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, raw, f"{exc.msg} (char {exc.pos})"
    return True, json.dumps(parsed, ensure_ascii=False, separators=(",", ":")), None


def validate_json_columns(df, json_columns: list[str]):
    normalized_df = df.copy()
    invalid_examples: list[dict[str, str | int]] = []
    invalid_row_numbers: set[int] = set()

    for column in json_columns:
        for index, value in normalized_df[column].items():
            is_valid, normalized_value, error_message = normalize_json_value(value)
            if is_valid:
                normalized_df.at[index, column] = normalized_value
                continue

            row_number = int(index) + 2
            invalid_row_numbers.add(row_number)
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        "row": row_number,
                        "column": column,
                        "value": str(value),
                        "error": error_message or "invalid JSON",
                    }
                )

    return normalized_df, len(invalid_row_numbers), invalid_examples


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    import pandas as pd
    from src.database import DatabaseManager

    table_name = args.table
    if not table_name or not TABLE_NAME_RE.match(table_name):
        print("[ERROR] TARGET_TABLE or --table must be a single table name.")
        return 1

    if args.batch_size <= 0:
        print("[ERROR] --batch-size must be greater than 0.")
        return 1

    pk_columns = parse_column_list(args.pk_cols)
    configured_json_columns = parse_column_list(args.json_cols)
    if not pk_columns:
        print("[ERROR] PRIMARY_KEY_COLUMNS is required for insert_csv.py.")
        return 1

    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))
    input_path = Path(args.input) if args.input else csv_base_dir / table_name / "generated.csv"
    if not input_path.exists():
        print(f"[ERROR] Generated CSV not found: {input_path}")
        return 1

    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    if df.empty:
        print("[ERROR] Generated CSV is empty.")
        return 1

    missing_pk_columns = [column for column in pk_columns if column not in df.columns]
    if missing_pk_columns:
        print(f"[ERROR] PRIMARY_KEY_COLUMNS not found in CSV: {missing_pk_columns}")
        return 1

    missing_configured_json_columns = [column for column in configured_json_columns if column not in df.columns]
    if missing_configured_json_columns:
        print(f"[ERROR] JSON_COLUMNS not found in CSV: {missing_configured_json_columns}")
        return 1

    if args.skip_db_check and not args.dry_run:
        print("[ERROR] --skip-db-check can only be used together with --dry-run.")
        return 1

    db = None
    json_columns = configured_json_columns
    prepared_df = df

    try:
        total_rows = len(df)
        null_pk_rows = count_empty_pk_rows(df, pk_columns)
        duplicate_pk_rows = count_duplicate_pk_rows(df, pk_columns)

        print(f"Target table: {table_name}")
        print(f"CSV path: {input_path}")
        print(f"Total rows: {total_rows}")
        print(f"Columns: {', '.join(df.columns)}")
        print(f"Batch size: {args.batch_size}")
        print(f"Primary key columns: {', '.join(pk_columns)}")
        print(f"Empty primary key rows: {null_pk_rows}")
        print(f"Duplicate primary key rows inside CSV: {duplicate_pk_rows}")

        if args.skip_db_check:
            print("Database schema check: skipped")
        else:
            db = DatabaseManager()
            if not db.connect():
                print("[ERROR] Database connection failed.")
                return 1

            table_description = db.describe_table(table_name)
            table_columns = [column[0] for column in table_description]
            json_columns = sorted(set(configured_json_columns) | set(detect_json_columns(table_description)))
            unknown_columns = [column for column in df.columns if column not in table_columns]
            if unknown_columns:
                print(f"[ERROR] CSV contains columns that do not exist in the table: {unknown_columns}")
                return 1

        missing_json_columns = [column for column in json_columns if column not in df.columns]
        if missing_json_columns:
            print(f"[ERROR] JSON columns not found in CSV: {missing_json_columns}")
            return 1

        prepared_df, invalid_json_rows, invalid_json_examples = validate_json_columns(df, json_columns)
        print(f"JSON columns: {', '.join(json_columns) if json_columns else '(none)'}")
        print(f"Invalid JSON rows: {invalid_json_rows}")
        if invalid_json_examples:
            print("Invalid JSON examples:")
            for example in invalid_json_examples:
                print(
                    f"  row {example['row']} column {example['column']}: "
                    f"{example['error']} | value={example['value']}"
                )

        if null_pk_rows > 0 or duplicate_pk_rows > 0:
            print("[ERROR] Dry-run failed because the CSV contains invalid primary key values.")
            return 1
        if invalid_json_rows > 0:
            print("[ERROR] Dry-run failed because the CSV contains invalid JSON values.")
            return 1

        if args.dry_run:
            print("[OK] Dry-run passed. No rows were inserted.")
            return 0

        insert_columns = list(df.columns)
        sql_columns = ", ".join(f"`{column}`" for column in insert_columns)
        placeholders = ", ".join(["%s"] * len(insert_columns))
        sql = f"INSERT INTO `{table_name}` ({sql_columns}) VALUES ({placeholders})"

        work_df = prepared_df.astype(object).replace("", None)
        records = work_df.to_dict(orient="records")

        inserted = 0
        for start in range(0, total_rows, args.batch_size):
            batch = records[start : start + args.batch_size]
            values = [tuple(record[column] for column in insert_columns) for record in batch]
            db.executemany(sql, values)
            inserted += len(batch)
            print(f"[OK] Inserted {inserted}/{total_rows} rows")

        print(f"[DONE] Insert completed: {inserted} rows inserted into {table_name}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Insert failed: {exc}")
        return 1
    finally:
        if db is not None:
            db.disconnect()


if __name__ == "__main__":
    sys.exit(main())
