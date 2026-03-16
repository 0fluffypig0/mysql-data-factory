"""
MySQL Data Factory
==================
批量数据库操作工具集

功能:
- 数据库连接管理
- 批量数据插入
- 测试数据生成
- 数据模板加载
"""

__version__ = "1.0.0"
__author__ = "WJC"
__email__ = "wwang.jc.jp@gmail.com"

# 导出核心类
from .database import DatabaseManager
from .data_generator import DataGenerator
from .bulk_inserter import BulkInserter
from .data_loader import DataLoader

__all__ = [
    'DatabaseManager',
    'DataGenerator', 
    'BulkInserter',
    'DataLoader'
]