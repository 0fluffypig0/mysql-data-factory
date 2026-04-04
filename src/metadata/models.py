"""
Core metadata models for database scan results.

All models are dataclass-based, JSON-serializable, and shared across GUI/CLI/workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class ColumnMetadata:
    """Metadata for a single database column."""

    name: str
    data_type: str  # e.g. "varchar", "int", "bigint", "json", "datetime"
    column_type: str  # e.g. "varchar(255)", "bigint(20)"
    is_nullable: bool = True
    column_default: str | None = None
    is_primary_key: bool = False
    is_unique_key: bool = False
    is_auto_increment: bool = False
    is_json: bool = False
    is_time_field: bool = False
    is_potential_marker: bool = False  # remark/source/created_by/memo etc.
    max_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnMetadata:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TableMetadata:
    """Complete metadata for one database table."""

    table_name: str
    database_name: str = ""
    columns: list[ColumnMetadata] = field(default_factory=list)
    primary_key_columns: list[str] = field(default_factory=list)
    unique_key_columns: list[str] = field(default_factory=list)
    json_columns: list[str] = field(default_factory=list)
    auto_increment_columns: list[str] = field(default_factory=list)
    time_columns: list[str] = field(default_factory=list)
    marker_columns: list[str] = field(default_factory=list)
    column_order: list[str] = field(default_factory=list)
    row_count: int = 0
    max_pk_value: Any = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["columns"] = [c.to_dict() for c in self.columns]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TableMetadata:
        columns_data = data.pop("columns", [])
        columns = [ColumnMetadata.from_dict(c) for c in columns_data]
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(columns=columns, **filtered)

    @property
    def pk_display(self) -> str:
        return ", ".join(self.primary_key_columns) if self.primary_key_columns else "(none)"

    @property
    def has_auto_increment_pk(self) -> bool:
        return any(c in self.auto_increment_columns for c in self.primary_key_columns)


@dataclass
class DatabaseScanResult:
    """Complete scan result for a database."""

    database_name: str
    tables: dict[str, TableMetadata] = field(default_factory=dict)
    scan_time: str = ""
    scan_version: str = "2.0"

    def __post_init__(self):
        if not self.scan_time:
            self.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_name": self.database_name,
            "scan_time": self.scan_time,
            "scan_version": self.scan_version,
            "table_count": len(self.tables),
            "tables": {name: meta.to_dict() for name, meta in self.tables.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatabaseScanResult:
        tables_data = data.get("tables", {})
        tables = {name: TableMetadata.from_dict(meta) for name, meta in tables_data.items()}
        return cls(
            database_name=data.get("database_name", ""),
            tables=tables,
            scan_time=data.get("scan_time", ""),
            scan_version=data.get("scan_version", "2.0"),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> DatabaseScanResult:
        return cls.from_dict(json.loads(json_str))

    @property
    def table_names(self) -> list[str]:
        return sorted(self.tables.keys())
