"""
批量插入模块
============
负责数据验证、批量插入、事务管理
"""

import pandas as pd
from typing import List, Dict, Any
from loguru import logger
import sys
from .database import DatabaseManager

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


class BulkInserter:
    """
    批量插入器
    
    用法:
        with DatabaseManager() as db:
            inserter = BulkInserter(db)
            inserter.insert_from_dataframe(df, 'table_name')
    """
    
    def __init__(self, db: DatabaseManager):
        """
        初始化插入器
        
        Args:
            db: DatabaseManager实例
        """
        self.db = db
        self.total_inserted = 0
        self.total_failed = 0
    
    def validate_data(self, df: pd.DataFrame, table_name: str) -> bool:
        """
        验证数据（基础验证）
        
        Args:
            df: 数据 DataFrame
            table_name: 表名
            
        Returns:
            bool: 验证是否通过
        """
        logger.info(f"验证数据：{len(df)} 行")
        
        # 1. 检查空值
        null_counts = df.isnull().sum()
        if null_counts.any():
            logger.warning(f"发现空值:\n{null_counts[null_counts > 0]}")
        
        # 2. 检查列是否匹配
        try:
            table_cols = [col[0] for col in self.db.describe_table(table_name)]
            df_cols = list(df.columns)
            
            missing_cols = set(df_cols) - set(table_cols)
            if missing_cols:
                logger.warning(f"DataFrame中有表中不存在的列: {missing_cols}")
        except Exception as e:
            logger.warning(f"无法获取表结构进行验证: {e}")
        
        return True
    
    def insert_from_dataframe(self, df: pd.DataFrame, table_name: str, 
                             batch_size: int = 1000) -> int:
        """
        从 DataFrame 批量插入
        
        Args:
            df: 数据 DataFrame
            table_name: 表名
            batch_size: 每批插入数量
            
        Returns:
            成功插入的行数
        """
        if df.empty:
            logger.warning("没有数据可插入")
            return 0
        
        # 验证数据
        if not self.validate_data(df, table_name):
            logger.error("数据验证失败")
            return 0
        
        total = len(df)
        inserted = 0
        
        logger.info(f"开始插入到表：{table_name}")
        logger.info(f"总记录数：{total}, 批次大小：{batch_size}")
        
        # 转换为列表
        records = df.to_dict('records')
        columns = list(df.columns)
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
        
        try:
            # 分批插入
            for i in range(0, total, batch_size):
                batch = records[i:i+batch_size]
                values_batch = [tuple(record[col] for col in columns) for record in batch]
                
                count = self.db.executemany(sql, values_batch)
                inserted += count
                
                progress = (inserted / total) * 100
                logger.info(f"进度：{inserted}/{total} ({progress:.1f}%)")
            
            self.total_inserted += inserted
            logger.success(f"✓ 插入完成！共插入 {inserted} 条记录")
            return inserted
            
        except Exception as e:
            logger.error(f"✗ 批量插入失败：{e}")
            self.total_failed += total - inserted
            raise
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            "inserted": self.total_inserted,
            "failed": self.total_failed
        }