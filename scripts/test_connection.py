#!/usr/bin/env python3
"""Validate database connectivity for the minimal CSV workflow."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def parse_args() -> argparse.Namespace:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument("--env-file", default=".env")
    env_args, _ = env_parser.parse_known_args()
    maybe_load_dotenv(env_args.env_file)

    parser = argparse.ArgumentParser(description="Test database connectivity from .env.")
    parser.add_argument(
        "--env-file",
        default=env_args.env_file,
        help="Path to the env file. Defaults to .env in the project root.",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("TARGET_TABLE"),
        help="Optional table name to verify after SELECT 1.",
    )
    return parser.parse_args()


def table_exists(db, table_name: str) -> bool:
    rows = db.query("SHOW TABLES LIKE %s", (table_name,))
    return bool(rows)


def main() -> int:
    args = parse_args()
    from src.database import DatabaseManager

    db = DatabaseManager()
    print(f"Host: {db.host}")
    print(f"Port: {db.port}")
    print(f"Database: {db.database}")

    if not db.connect():
        print("[FAIL] Database connection failed.")
        return 1

    try:
        db.query("SELECT 1")
        print("[OK] SELECT 1 succeeded.")

        if args.table:
            if table_exists(db, args.table):
                print(f"[OK] Target table exists: {args.table}")
            else:
                print(f"[FAIL] Target table not found: {args.table}")
                return 1

        print("[DONE] Connectivity check passed.")
        return 0
    except Exception as exc:
        print(f"[FAIL] Connectivity check failed: {exc}")
        return 1
    finally:
        db.disconnect()


if __name__ == "__main__":
    sys.exit(main())
