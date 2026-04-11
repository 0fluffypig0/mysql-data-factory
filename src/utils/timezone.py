"""
Timezone utilities.

All timestamps in MySQL Data Factory 3.00 use Asia/Tokyo (JST).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

# JST = UTC+9
JST = timezone(timedelta(hours=9), name="JST")


def now_jst() -> datetime:
    """Get current time in JST."""
    return datetime.now(JST)


def now_jst_str(fmt: str = "%Y-%m-%d %H:%M:%S JST") -> str:
    """Get current time as formatted JST string."""
    return now_jst().strftime(fmt)


def now_jst_compact() -> str:
    """Compact timestamp for IDs: 20260401_102345"""
    return now_jst().strftime("%Y%m%d_%H%M%S")


def format_jst(dt: datetime | str | None, fmt: str = "%Y-%m-%d %H:%M:%S JST") -> str:
    """Format a datetime or string as JST display string."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        if not dt:
            return ""
        # Try parsing common formats
        for parse_fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S JST", "%Y%m%d_%H%M%S"):
            try:
                dt = datetime.strptime(dt.replace(" JST", ""), parse_fmt)
                break
            except ValueError:
                continue
        else:
            return dt  # Can't parse, return as-is
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST).strftime(fmt)

