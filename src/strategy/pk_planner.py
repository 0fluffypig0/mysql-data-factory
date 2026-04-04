"""
Primary key range planning.

Supports multiple PK patterns:
- Pure integer (int/bigint): auto_increment_from_max, fixed_start, explicit_range
- Zero-padded string numbers: "0000000001" style
- Prefix + number: "KC0007", "AXC000000997" style
- Composite keys
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from loguru import logger

# Pattern to detect numeric-only strings (with possible leading zeros)
INTEGER_RE = re.compile(r"^-?\d+$")

# Pattern to detect prefix + numeric suffix (e.g. "KC0007", "AXC000000997")
PREFIX_NUM_RE = re.compile(r"^([A-Za-z_]+)(\d+)$")


@dataclass
class PKRangeConfig:
    """Configuration for a primary key range."""

    mode: str = "auto_increment_from_max"  # auto_increment_from_max | fixed_start | explicit_range
    start_value: int | None = None
    end_value: int | None = None
    prefix: str = ""
    zero_pad_width: int = 0
    total_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PKRangeConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def analyze_pk_pattern(sample_value: Any) -> dict[str, Any]:
    """
    Analyze a sample PK value to determine its pattern.

    Returns:
        dict with keys: type, prefix, numeric_part, zero_pad_width
    """
    if sample_value is None:
        return {"type": "unknown", "prefix": "", "numeric_part": None, "zero_pad_width": 0}

    str_val = str(sample_value).strip()

    # Pure integer
    if isinstance(sample_value, int):
        return {"type": "integer", "prefix": "", "numeric_part": sample_value, "zero_pad_width": 0}

    # Zero-padded numeric string: "0000000983"
    if INTEGER_RE.match(str_val):
        num = int(str_val)
        pad_width = len(str_val) if str_val.startswith("0") and len(str_val) > 1 else 0
        return {"type": "zero_padded" if pad_width else "integer_string", "prefix": "",
                "numeric_part": num, "zero_pad_width": pad_width}

    # Prefix + number: "KC0007", "AXC000000997"
    m = PREFIX_NUM_RE.match(str_val)
    if m:
        prefix = m.group(1)
        num_str = m.group(2)
        num = int(num_str)
        pad_width = len(num_str) if num_str.startswith("0") and len(num_str) > 1 else len(num_str)
        return {"type": "prefix_number", "prefix": prefix,
                "numeric_part": num, "zero_pad_width": pad_width}

    return {"type": "string", "prefix": "", "numeric_part": None, "zero_pad_width": 0}


def format_pk_value(numeric_value: int, pattern: dict[str, Any]) -> str:
    """Format a numeric value according to the analyzed PK pattern."""
    pk_type = pattern.get("type", "unknown")
    prefix = pattern.get("prefix", "")
    pad_width = pattern.get("zero_pad_width", 0)

    if pk_type == "integer":
        return str(numeric_value)

    if pk_type in ("zero_padded", "integer_string"):
        if pad_width > 0:
            return str(numeric_value).zfill(pad_width)
        return str(numeric_value)

    if pk_type == "prefix_number":
        if pad_width > 0:
            return f"{prefix}{str(numeric_value).zfill(pad_width)}"
        return f"{prefix}{numeric_value}"

    return str(numeric_value)


def plan_pk_range(
    config: PKRangeConfig,
    sample_value: Any,
    current_max: Any = None,
    row_count: int = 0,
) -> list[str]:
    """
    Generate a list of PK values based on the range config.

    Returns a list of string PK values.
    """
    pattern = analyze_pk_pattern(sample_value)
    total = config.total_count or row_count

    if total <= 0:
        return []

    # Override pattern with explicit config if provided
    if config.prefix:
        pattern["prefix"] = config.prefix
    if config.zero_pad_width > 0:
        pattern["zero_pad_width"] = config.zero_pad_width

    # Determine start value
    if config.mode == "fixed_start" and config.start_value is not None:
        start = config.start_value
    elif config.mode == "explicit_range" and config.start_value is not None:
        start = config.start_value
    elif config.mode == "auto_increment_from_max":
        if current_max is not None:
            max_pattern = analyze_pk_pattern(current_max)
            if max_pattern["numeric_part"] is not None:
                start = max_pattern["numeric_part"] + 1
            else:
                start = 1
        elif pattern["numeric_part"] is not None:
            start = pattern["numeric_part"] + 1
        else:
            start = 1
    else:
        start = config.start_value or 1

    # Determine end
    if config.mode == "explicit_range" and config.end_value is not None:
        end = config.end_value
        total = end - start + 1
    else:
        end = start + total - 1

    # Generate values
    values = []
    for i in range(total):
        values.append(format_pk_value(start + i, pattern))

    return values


def check_pk_conflict(db, table_name: str, pk_column: str,
                      planned_values: list[str], batch_size: int = 1000) -> list[str]:
    """
    Check if any planned PK values already exist in the database.

    Returns list of conflicting values.
    """
    conflicts = []
    for i in range(0, len(planned_values), batch_size):
        batch = planned_values[i:i + batch_size]
        placeholders = ",".join(["%s"] * len(batch))
        sql = f"SELECT `{pk_column}` FROM `{table_name}` WHERE `{pk_column}` IN ({placeholders})"
        rows = db.query(sql, tuple(batch))
        conflicts.extend(str(row[0]) for row in rows)

    if conflicts:
        logger.warning(f"Found {len(conflicts)} PK conflicts in {table_name}.{pk_column}")
    return conflicts


# --- Legacy compatibility ---

def is_integer_like(value: object) -> bool:
    """Check if a value looks like an integer."""
    if value is None:
        return False
    return INTEGER_RE.match(str(value).strip()) is not None


def format_integer_like(new_value: int, template_value: object) -> str:
    """Format an integer preserving the template's appearance (leading zeros etc.)."""
    raw_text = "" if template_value is None else str(template_value).strip()

    if raw_text.startswith("-"):
        raw_digits = raw_text[1:]
        if len(raw_digits) > 1 and raw_digits.startswith("0"):
            return f"-{abs(new_value):0{len(raw_digits)}d}"
        return str(new_value)

    if len(raw_text) > 1 and raw_text.startswith("0"):
        return str(new_value).zfill(len(raw_text))

    return str(new_value)


def increment_key_value(template_value: object, sequence_index: int,
                        start_value: int | None) -> str:
    """Generate a new key value by incrementing. Legacy compatible."""
    raw_text = "" if template_value is None else str(template_value)
    if raw_text == "":
        return raw_text

    if start_value is not None:
        if is_integer_like(raw_text):
            return format_integer_like(start_value + sequence_index, template_value)
        # Check prefix+number pattern
        m = PREFIX_NUM_RE.match(raw_text)
        if m:
            prefix = m.group(1)
            num_str = m.group(2)
            pad_width = len(num_str)
            new_num = start_value + sequence_index
            return f"{prefix}{str(new_num).zfill(pad_width)}"
        return f"{raw_text}_{start_value + sequence_index:06d}"

    if is_integer_like(raw_text):
        return format_integer_like(int(raw_text) + sequence_index, template_value)

    # Check prefix+number pattern
    m = PREFIX_NUM_RE.match(raw_text)
    if m:
        prefix = m.group(1)
        num_str = m.group(2)
        pad_width = len(num_str)
        new_num = int(num_str) + sequence_index
        return f"{prefix}{str(new_num).zfill(pad_width)}"

    return f"{raw_text}_{sequence_index + 1:06d}"
