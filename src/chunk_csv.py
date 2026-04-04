"""
chunk CSV 读写工具。

V1.1 的大文件策略非常明确：

- 不一次性生成几十万条大 CSV
- 统一改成小块 chunk
- 每个 chunk 单独落盘、单独插入

这个文件只做一件事：

- 帮脚本把 chunk CSV 的读取、写入、命名方式统一起来
"""

from __future__ import annotations

import csv
from pathlib import Path


def ensure_chunk_size(chunk_size: int, max_chunk_size: int = 10000) -> int:
    """
    校验 chunk size。

    设计规则：

    - chunk size 必须大于 0
    - chunk size 不允许超过 10000

    这个上限是 V1.1 的硬性约束，用来避免堡垒机场景中再出现超大文件和内存压力。
    """

    if chunk_size <= 0:
        raise ValueError("chunk size must be greater than 0")
    if chunk_size > max_chunk_size:
        return max_chunk_size
    return chunk_size


def resolve_chunk_dir(csv_base_dir: Path, table_name: str) -> Path:
    """返回某张表的 chunk 目录。"""

    return csv_base_dir / table_name / "chunks"


def build_chunk_file_path(csv_base_dir: Path, table_name: str, chunk_index: int) -> Path:
    """按统一规则生成 chunk 文件名。"""

    chunk_dir = resolve_chunk_dir(csv_base_dir, table_name)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir / f"chunk_{chunk_index:06d}.csv"


def write_rows_to_csv(file_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """
    把一批行写成一个 CSV 文件。

    这里一次只写一个 chunk，不负责整批任务的循环。
    """

    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv_rows(file_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """
    读取整个小 CSV 文件。

    这里允许把整个文件读入内存，是因为 V1.1 已经把单个 chunk 的上限卡在 10000 行以内。
    也就是说，这个函数只适用于：
    - 单条模板文件
    - 单个 chunk 文件
    """

    with file_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def read_template_csv(file_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """
    读取模板 CSV。

    V1.1 主推只用 1 条模板记录，因此脚本层会拿这个函数的结果再明确判断：

    - 模板为空：报错
    - 模板超过 1 条：明确提示，只使用第一条
    """

    return read_csv_rows(file_path)


def list_chunk_files(input_path: Path) -> list[Path]:
    """
    列出待插入的 chunk 文件。

    支持两种输入：

    - 单个 CSV 文件
    - 一个包含多个 chunk CSV 的目录
    """

    if input_path.is_file():
        return [input_path]

    if input_path.is_dir():
        return sorted(
            [item for item in input_path.iterdir() if item.is_file() and item.suffix.lower() == ".csv"]
        )

    return []
