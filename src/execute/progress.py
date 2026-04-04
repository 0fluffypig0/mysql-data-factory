"""
Progress tracking dataclass for campaign execution.

Design goals:
- Single unified structure passed through all callbacks
- Lightweight (no heavy computation inside)
- Safe to emit across QThread boundary via Signal(object)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ProgressSnapshot:
    """Immutable-ish snapshot of execution progress at a point in time."""

    # --- Task context ---
    phase: str = ""          # "sample" | "generate" | "insert" | "done" | "error"
    task_idx: int = 0        # 1-based task index
    total_tasks: int = 0
    table_name: str = ""

    # --- Row counters ---
    total_rows: int = 0
    generated_rows: int = 0
    inserted_rows: int = 0

    # --- Chunk info (generate phase) ---
    chunk_idx: int = 0
    total_chunks: int = 0

    # --- Batch info (insert phase) ---
    batch_idx: int = 0
    total_batches: int = 0

    # --- Throughput ---
    rows_per_sec: float = 0.0
    eta_seconds: float = -1.0   # -1 = unknown

    # --- Wall clock (set by runner, not UI) ---
    timestamp: float = field(default_factory=time.monotonic)

    # --- Optional log message ---
    log_line: str = ""

    # --- Overall campaign progress (0.0 – 1.0) ---
    overall_fraction: float = 0.0

    def eta_str(self) -> str:
        if self.eta_seconds < 0:
            return "--:--"
        secs = int(self.eta_seconds)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m{secs % 60:02d}s"

    def speed_str(self) -> str:
        if self.rows_per_sec <= 0:
            return "--"
        if self.rows_per_sec >= 1000:
            return f"{self.rows_per_sec / 1000:.1f}k rows/s"
        return f"{self.rows_per_sec:.0f} rows/s"
