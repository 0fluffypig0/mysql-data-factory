"""
Field-level generation strategies.

Each column can have a strategy that determines how its value is generated:
- copy: Copy from template (default)
- pk_increment: Primary key auto-increment
- unique_increment: Unique key increment
- sample_choice: Random choice from sample values
- time_offset: Current time or offset from template
- marker: Test data marker injection
- db_default: Use database default value
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class FieldStrategy:
    """Strategy for generating a single field's value."""

    column_name: str
    strategy_type: str = "copy"  # copy | pk_increment | unique_increment | sample_choice | time_offset | marker | db_default
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldStrategy:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def infer_strategies(
    column_order: list[str],
    pk_columns: list[str],
    unique_columns: list[str],
    time_columns: list[str],
    marker_columns: list[str],
    marker_value: str = "",
) -> list[FieldStrategy]:
    """
    Auto-infer field strategies based on column metadata.

    PK columns -> pk_increment
    Unique columns (not PK) -> unique_increment
    Time columns -> time_offset (if update-related name) or copy
    Marker columns -> marker (if marker_value set) or copy
    Everything else -> copy
    """
    strategies = []
    update_time_hints = {"updated_at", "update_time", "modify_time", "modified_at", "update_date"}

    for col in column_order:
        if col in pk_columns:
            strategies.append(FieldStrategy(column_name=col, strategy_type="pk_increment"))
        elif col in unique_columns:
            strategies.append(FieldStrategy(column_name=col, strategy_type="unique_increment"))
        elif col in time_columns and col.lower() in update_time_hints:
            strategies.append(FieldStrategy(column_name=col, strategy_type="time_offset",
                                           params={"mode": "now"}))
        elif col in marker_columns and marker_value:
            strategies.append(FieldStrategy(column_name=col, strategy_type="marker",
                                           params={"value": marker_value}))
        else:
            strategies.append(FieldStrategy(column_name=col, strategy_type="copy"))

    return strategies
