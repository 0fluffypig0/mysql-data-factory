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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test database connectivity from .env.")
    parser.add_argument(
        "--table",
        default=os.getenv("TARGET_TABLE"),
        help="Optional table name to verify after SELECT 1.",
    )
    return parser.parse_args()


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def table_exists(db, table_name: str) -> bool:
    rows = db.query("SHOW TABLES LIKE %s", (table_name,))
    return bool(rows)


def main() -> int:
    maybe_load_dotenv()
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
