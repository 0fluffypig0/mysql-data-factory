"""
Multi-table task planning models.

Core models:
- TaskItem: Configuration for one table's data generation task
- CampaignPlan: A collection of TaskItems to execute as a batch
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.strategy.field_strategy import FieldStrategy
from src.strategy.pk_planner import PKRangeConfig


@dataclass
class TaskItem:
    """Configuration for generating test data for a single table."""

    table_name: str
    row_count: int = 1000
    batch_size: int = 1000
    mode: str = "insert"  # dry-run | export | insert

    # Sample selection
    sample_pk_value: str = ""
    sample_where: str = ""
    sample_method: str = "pk_lookup"  # pk_lookup | where_clause | first_row

    # Primary key range
    pk_config: PKRangeConfig = field(default_factory=PKRangeConfig)

    # Field strategies (auto-inferred if empty)
    field_strategies: list[FieldStrategy] = field(default_factory=list)

    # Test marker
    marker_column: str = ""
    marker_value: str = ""

    # Output
    output_dir: str = ""

    # Task ID
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pk_config"] = self.pk_config.to_dict()
        d["field_strategies"] = [s.to_dict() for s in self.field_strategies]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskItem:
        pk_data = data.pop("pk_config", {})
        strategies_data = data.pop("field_strategies", [])
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        item = cls(**filtered)
        item.pk_config = PKRangeConfig.from_dict(pk_data) if pk_data else PKRangeConfig()
        item.field_strategies = [FieldStrategy.from_dict(s) for s in strategies_data]
        return item

    def summary(self) -> str:
        return (f"[{self.task_id}] {self.table_name}: "
                f"{self.row_count} rows, batch={self.batch_size}, mode={self.mode}")


@dataclass
class CampaignPlan:
    """A collection of table tasks to execute as a batch."""

    campaign_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    name: str = ""
    tasks: list[TaskItem] = field(default_factory=list)
    database_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "draft"  # draft | confirmed | running | completed | failed

    def add_task(self, task: TaskItem) -> None:
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        self.tasks = [t for t in self.tasks if t.task_id != task_id]

    def get_task(self, task_id: str) -> TaskItem | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tasks)

    @property
    def table_count(self) -> int:
        return len(self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "name": self.name,
            "database_name": self.database_name,
            "created_at": self.created_at,
            "status": self.status,
            "table_count": self.table_count,
            "total_rows": self.total_rows,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CampaignPlan:
        tasks_data = data.pop("tasks", [])
        # Remove computed properties
        data.pop("table_count", None)
        data.pop("total_rows", None)
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        plan = cls(**filtered)
        plan.tasks = [TaskItem.from_dict(t) for t in tasks_data]
        return plan

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> CampaignPlan:
        return cls.from_dict(json.loads(json_str))

    def save(self, plans_dir: Path) -> Path:
        plans_dir.mkdir(parents=True, exist_ok=True)
        path = plans_dir / f"campaign_{self.campaign_id}.json"
        with path.open("w", encoding="utf-8") as f:
            f.write(self.to_json())
            f.write("\n")
        return path

    @classmethod
    def load(cls, path: Path) -> CampaignPlan:
        with path.open("r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    def summary(self) -> str:
        lines = [
            f"Campaign: {self.campaign_id}",
            f"Name: {self.name or '(unnamed)'}",
            f"Database: {self.database_name}",
            f"Tables: {self.table_count}, Total rows: {self.total_rows}",
            f"Status: {self.status}",
            "",
        ]
        for i, task in enumerate(self.tasks, 1):
            lines.append(f"  {i}. {task.summary()}")
        return "\n".join(lines)
