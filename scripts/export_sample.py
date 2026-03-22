#!/usr/bin/env python3
"""Export a small sample from a single target table to CSV."""

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


def parse_column_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def detect_json_columns(table_description: list[tuple]) -> list[str]:
    return [str(column[0]) for column in table_description if len(column) > 1 and "json" in str(column[1]).lower()]


def normalize_json_for_csv(value: object) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return ""
        parsed = json.loads(raw)
    else:
        parsed = value

    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()
    maybe_load_dotenv(env_args.env_file)

    parser = argparse.ArgumentParser(description="Export sample records from one table to CSV.")
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )
    parser.add_argument("--table", default=os.getenv("TARGET_TABLE"))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("EXPORT_SAMPLE_LIMIT", "3")),
    )
    parser.add_argument("--output")
    return parser.parse_args()


def validate_table_name(table_name: str) -> str:
    if not table_name or not TABLE_NAME_RE.match(table_name):
        raise ValueError("A single table name is required and may only contain letters, numbers, and underscores.")
    return table_name


def main() -> int:
    args = parse_args()
    from src.database import DatabaseManager

    try:
        table_name = validate_table_name(args.table)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if args.limit <= 0:
        print("[ERROR] --limit must be greater than 0.")
        return 1

    csv_base_dir = Path(os.getenv("CSV_BASE_DIR", "data"))
    output_path = Path(args.output) if args.output else csv_base_dir / table_name / "sample.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    db = DatabaseManager()
    if not db.connect():
        print("[ERROR] Database connection failed.")
        return 1

    try:
        table_description = db.describe_table(table_name)
        configured_json_columns = parse_column_list(os.getenv("JSON_COLUMNS"))
        json_columns = sorted(set(configured_json_columns) | set(detect_json_columns(table_description)))
        sql = f"SELECT * FROM `{table_name}` LIMIT {args.limit}"
        df = db.to_dataframe(sql)
        for column in json_columns:
            if column in df.columns:
                df[column] = df[column].map(normalize_json_for_csv)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[OK] Exported {len(df)} rows from {table_name}.")
        print(f"Output: {output_path}")
        print(f"JSON columns: {json_columns if json_columns else '(none)'}")
        print("Next step: manually edit this CSV and save it as template.csv.")
        return 0
    except Exception as exc:
        print(f"[ERROR] Export failed: {exc}")
        return 1
    finally:
        db.disconnect()


if __name__ == "__main__":
    sys.exit(main())
