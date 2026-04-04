"""
Common utility functions.

Migrated and extended from V1.1 src/utils.py.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru for console output."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    )


def get_timestamp() -> str:
    """Get current timestamp string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_bytes(size: int) -> str:
    """Format byte size to human readable."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def validate_table_name(table_name: str | None) -> str | None:
    """Validate table name: letters, numbers, underscores only."""
    if table_name is None or table_name == "":
        return None
    if not TABLE_NAME_RE.match(table_name):
        raise ValueError("Table name may only contain letters, numbers, and underscores.")
    return table_name


def parse_column_list(raw_value: str | None) -> list[str]:
    """Parse comma-separated column names."""
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]
