"""
Sample data selection.

Supports multiple ways to pick a sample record from a database table:
- By primary key value
- By custom WHERE clause
- By querying recent/top rows
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from src.db.connection import DatabaseManager


@dataclass
class SampleSelection:
    """A selected sample record with metadata."""

    table_name: str
    row_data: dict[str, Any] = field(default_factory=dict)
    column_order: list[str] = field(default_factory=list)
    selection_method: str = ""  # "pk_lookup", "where_clause", "first_row"
    selection_criteria: str = ""  # The actual PK value or WHERE clause used

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SampleSelection:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def summary(self) -> str:
        pk_display = self.selection_criteria or "(unknown)"
        col_count = len(self.row_data)
        return f"Table: {self.table_name}, Method: {self.selection_method}, Key: {pk_display}, Columns: {col_count}"


def select_by_pk(db: DatabaseManager, table_name: str,
                 pk_columns: list[str], pk_values: list[Any]) -> SampleSelection | None:
    """Select a sample record by primary key value(s)."""

    if len(pk_columns) != len(pk_values):
        raise ValueError(f"PK columns count ({len(pk_columns)}) != values count ({len(pk_values)})")

    where_parts = [f"`{col}` = %s" for col in pk_columns]
    where_clause = " AND ".join(where_parts)
    sql = f"SELECT * FROM `{table_name}` WHERE {where_clause} LIMIT 1"

    rows = db.query_dicts(sql, tuple(pk_values))
    if not rows:
        return None

    column_order = db.get_column_names(table_name)
    criteria = ", ".join(f"{c}={v}" for c, v in zip(pk_columns, pk_values))

    return SampleSelection(
        table_name=table_name,
        row_data=rows[0],
        column_order=column_order,
        selection_method="pk_lookup",
        selection_criteria=criteria,
    )


def select_by_where(db: DatabaseManager, table_name: str,
                    where_clause: str) -> list[SampleSelection]:
    """Select sample records using a custom WHERE clause."""

    sql = f"SELECT * FROM `{table_name}` WHERE {where_clause} LIMIT 10"
    rows = db.query_dicts(sql)
    column_order = db.get_column_names(table_name)

    results = []
    for row in rows:
        results.append(SampleSelection(
            table_name=table_name,
            row_data=row,
            column_order=column_order,
            selection_method="where_clause",
            selection_criteria=where_clause,
        ))
    return results


def select_top_rows(db: DatabaseManager, table_name: str,
                    limit: int = 5) -> list[SampleSelection]:
    """Select top N rows from a table."""

    sql = f"SELECT * FROM `{table_name}` LIMIT {int(limit)}"
    rows = db.query_dicts(sql)
    column_order = db.get_column_names(table_name)

    results = []
    for row in rows:
        results.append(SampleSelection(
            table_name=table_name,
            row_data=row,
            column_order=column_order,
            selection_method="first_row",
            selection_criteria=f"LIMIT {limit}",
        ))
    return results


def normalize_sample_for_csv(row_data: dict[str, Any]) -> dict[str, str]:
    """Convert a sample row dict to string values suitable for CSV/template."""
    result = {}
    for key, value in row_data.items():
        if value is None:
            result[key] = ""
        elif isinstance(value, (dict, list)):
            result[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            result[key] = str(value)
    return result


def save_sample_csv(sample: SampleSelection, output_path: Path) -> Path:
    """Save a sample selection as a CSV template file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    col_order = sample.column_order or list(sample.row_data.keys())
    row = normalize_sample_for_csv(sample.row_data)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=col_order)
        writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in col_order})

    logger.info(f"Sample saved to {output_path}")
    return output_path
