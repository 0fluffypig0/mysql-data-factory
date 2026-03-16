"""
数据库连接模块
==============
提供MySQL数据库连接和管理功能
"""

import pymysql
from dotenv import load_dotenv
import os
from typing import List, Dict, Any, Optional
import pandas as pd
from loguru import logger
import sys

# 加载环境变量
load_dotenv()

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO", 
           format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")


class DatabaseManager:
    """
    数据库管理器
    
    用法:
        # 方式1: 手动管理连接
        db = DatabaseManager()
        db.connect()
        result = db.query("SELECT * FROM table")
        db.disconnect()
        
        # 方式2: 上下文管理器（推荐）
        with DatabaseManager() as db:
            result = db.query("SELECT * FROM table")
    """
    
    def __init__(self, database: str = None):
        """
        初始化数据库管理器
        
        Args:
            database: 数据库名（不传则使用.env中的DB_NAME）
        """
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = int(os.getenv('DB_PORT', 3306))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = database or os.getenv('DB_NAME')
        self.charset = os.getenv('DB_CHARSET', 'utf8mb4')
        self.conn = None
        logger.info(f"初始化数据库管理器: {self.database}")
    
    def connect(self) -> bool:
        """
        连接数据库
        
        Returns:
            bool: 连接成功返回True
        """
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset
            )
            logger.success(f"✓ 成功连接到数据库: {self.database}")
            return True
        except Exception as e:
            logger.error(f"✗ 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("✓ 数据库连接已关闭")
    
    def query(self, sql: str, params: tuple = None) -> List[tuple]:
        """
        执行查询SQL
        
        Args:
            sql: SQL语句
            params: 参数元组
            
        Returns:
            查询结果列表
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params or ())
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"✗ 查询失败: {e}")
            raise
    
    def execute(self, sql: str, params: tuple = None) -> int:
        """
        执行增删改SQL
        
        Args:
            sql: SQL语句
            params: 参数元组
            
        Returns:
            受影响的行数
        """
        try:
            with self.conn.cursor() as cursor:
                result = cursor.execute(sql, params or ())
                self.conn.commit()
                return result
        except Exception as e:
            self.conn.rollback()
            logger.error(f"✗ 执行失败: {e}")
            raise
    
    def executemany(self, sql: str, params_list: List[tuple]) -> int:
        """
        批量执行SQL
        
        Args:
            sql: SQL语句
            params_list: 参数列表
            
        Returns:
            受影响的行数
        """
        try:
            with self.conn.cursor() as cursor:
                result = cursor.executemany(sql, params_list)
                self.conn.commit()
                return result
        except Exception as e:
            self.conn.rollback()
            logger.error(f"✗ 批量执行失败: {e}")
            raise
    
    def to_dataframe(self, sql: str) -> pd.DataFrame:
        """
        查询并返回DataFrame
        
        Args:
            sql: SQL语句
            
        Returns:
            pandas DataFrame
        """
        return pd.read_sql(sql, self.conn)
    
    def show_tables(self) -> List[str]:
        """显示所有表名"""
        result = self.query("SHOW TABLES")
        return [table[0] for table in result]
    
    def describe_table(self, table_name: str) -> List[tuple]:
        """查看表结构"""
        return self.query(f"DESCRIBE {table_name}")
    
    def count_rows(self, table_name: str) -> int:
        """统计表行数"""
        result = self.query(f"SELECT COUNT(*) FROM {table_name}")
        return result[0][0]
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()