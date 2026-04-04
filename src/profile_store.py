"""
表配置文件读写工具。

V1.1 新增这个文件的目的只有一个：

- 把“扫描出来的表信息”保存成一个简单 JSON 文件

这里不用 YAML，不用数据库，不用复杂配置框架。
原因很简单：

- JSON 是标准库就能处理的
- 内容结构直观
- 安全评审时更容易解释
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "config" / "table_profiles.json"


def resolve_profile_path(profile_path: str | None = None) -> Path:
    """
    解析表配置文件路径。

    优先级：

    1. 函数参数
    2. 环境变量 TABLE_PROFILE_PATH
    3. 默认路径 config/table_profiles.json
    """

    raw_path = profile_path or os.getenv("TABLE_PROFILE_PATH")
    if not raw_path:
        return DEFAULT_PROFILE_PATH

    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def create_empty_profile_store(database_name: str = "") -> dict[str, Any]:
    """创建一个空的表配置结构。"""

    return {
        "database": database_name,
        "tables": {},
    }


def load_profile_store(profile_path: str | None = None) -> tuple[Path, dict[str, Any]]:
    """
    读取表配置文件。

    如果文件不存在，则返回一个空结构，不直接报错。
    这样新仓库首次扫描表信息时可以直接写入。
    """

    path = resolve_profile_path(profile_path)
    if not path.exists():
        return path, create_empty_profile_store()

    # 这里使用 utf-8-sig，是为了兼容 Windows 上常见的带 BOM JSON 文件。
    # 这样可以减少“文件其实没问题，但因为编码头被解析失败”的现场问题。
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if "tables" not in data or not isinstance(data["tables"], dict):
        data["tables"] = {}

    if "database" not in data:
        data["database"] = ""

    return path, data


def save_profile_store(profile_data: dict[str, Any], profile_path: str | None = None) -> Path:
    """
    保存表配置文件。

    写入前会自动创建目录。
    """

    path = resolve_profile_path(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(profile_data, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return path


def get_table_profile(profile_path: str | None, table_name: str) -> dict[str, Any] | None:
    """读取指定表的配置。不存在时返回 None。"""

    _, profile_data = load_profile_store(profile_path)
    return profile_data.get("tables", {}).get(table_name)


def save_table_profile(
    table_name: str,
    table_profile: dict[str, Any],
    database_name: str = "",
    profile_path: str | None = None,
) -> Path:
    """
    保存单张表的配置。

    这里采用“读整个 JSON -> 更新一张表 -> 再写回去”的方式。
    代码虽然看起来更笨一点，但逻辑最直白。
    """

    path, profile_data = load_profile_store(profile_path)

    if database_name:
        profile_data["database"] = database_name

    tables = profile_data.setdefault("tables", {})
    tables[table_name] = table_profile

    return save_profile_store(profile_data, str(path))
