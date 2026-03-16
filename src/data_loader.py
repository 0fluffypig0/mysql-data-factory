"""
数据加载模块
============
负责读取数据模板、样本文件，支持多种格式
"""

import pandas as pd
import os
from pathlib import Path
from loguru import logger
import sys
import json
from datetime import datetime

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


class DataLoader:
    """
    数据加载器
    
    用法:
        loader = DataLoader()
        
        # 加载样本文件
        df = loader.load_sample('t_legal', file_type='csv')
        
        # 加载待插入文件
        df = loader.load_pending('data/pending/my_data.csv')
        
        # 保存样本
        loader.save_sample(df, 't_legal', file_type='csv')
    """
    
    def __init__(self, data_dir: str = "data"):
        """
        初始化加载器
        
        Args:
            data_dir: 数据根目录
        """
        self.data_dir = Path(data_dir)
        self.templates_dir = self.data_dir / "templates"
        self.samples_dir = self.data_dir / "samples"
        self.pending_dir = self.data_dir / "pending"
        self.output_dir = self.data_dir / "output"
        
        # 确保目录存在
        for dir_path in [self.templates_dir, self.samples_dir, self.pending_dir, self.output_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"初始化数据加载器，数据目录: {self.data_dir}")
    
    def load_template(self, table_name: str, file_type: str = "csv") -> pd.DataFrame:
        """
        加载模板文件
        
        Args:
            table_name: 表名
            file_type: 文件类型 (csv, excel, json)
            
        Returns:
            DataFrame
        """
        # 查找模板文件
        pattern = f"{table_name}_template.{file_type}"
        files = list(self.templates_dir.glob(pattern))
        
        if not files:
            raise FileNotFoundError(f"未找到模板文件：{pattern}")
        
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        logger.info(f"加载模板文件：{latest_file}")
        
        return self._read_file(latest_file, file_type)
    
    def load_sample(self, table_name: str, file_type: str = "csv") -> pd.DataFrame:
        """
        加载样本文件（最新的一条记录）
        
        Args:
            table_name: 表名
            file_type: 文件类型 (csv, excel, json)
            
        Returns:
            DataFrame
        """
        # 查找最新的样本文件
        pattern = f"{table_name}_*.{file_type}"
        files = list(self.samples_dir.glob(pattern))
        
        if not files:
            raise FileNotFoundError(f"未找到样本文件：{pattern}")
        
        # 按修改时间排序，取最新的
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        logger.info(f"加载样本文件：{latest_file}")
        
        return self._read_file(latest_file, file_type)
    
    def load_pending(self, file_path: str) -> pd.DataFrame:
        """
        加载待插入文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            DataFrame
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        
        file_type = path.suffix.replace('.', '')
        logger.info(f"加载待插入文件：{path}")
        
        return self._read_file(path, file_type)
    
    def _read_file(self, file_path: Path, file_type: str) -> pd.DataFrame:
        """内部方法：读取文件"""
        try:
            if file_type == "csv":
                return pd.read_csv(file_path, encoding='utf-8-sig')
            elif file_type in ["xlsx", "xls"]:
                return pd.read_excel(file_path)
            elif file_type == "json":
                return pd.read_json(file_path)
            else:
                raise ValueError(f"不支持的文件类型：{file_type}")
        except Exception as e:
            logger.error(f"读取文件失败：{e}")
            raise
    
    def save_sample(self, df: pd.DataFrame, table_name: str, file_type: str = "csv") -> str:
        """
        保存样本文件（自动加时间戳）
        
        Args:
            df: DataFrame
            table_name: 表名
            file_type: 文件类型
            
        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_{timestamp}.{file_type}"
        file_path = self.samples_dir / filename
        
        if file_type == "csv":
            df.to_csv(file_path, index=False, encoding="utf-8-sig")
        elif file_type in ["xlsx", "xls"]:
            df.to_excel(file_path, index=False)
        elif file_type == "json":
            df.to_json(file_path, orient="records", force_ascii=False, indent=2)
        
        logger.success(f"样本已保存：{file_path}")
        return str(file_path)
    
    def save_pending(self, df: pd.DataFrame, filename: str = "pending_insert.csv") -> str:
        """
        保存待插入文件
        
        Args:
            df: DataFrame
            filename: 文件名
            
        Returns:
            保存的文件路径
        """
        file_path = self.pending_dir / filename
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        logger.success(f"待插入文件已保存：{file_path}")
        return str(file_path)
    
    def save_output(self, df: pd.DataFrame, filename: str) -> str:
        """
        保存输出文件
        
        Args:
            df: DataFrame
            filename: 文件名
            
        Returns:
            保存的文件路径
        """
        file_path = self.output_dir / filename
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        logger.success(f"输出文件已保存：{file_path}")
        return str(file_path)
    
    def list_samples(self, table_name: str = None) -> List[str]:
        """
        列出所有样本文件
        
        Args:
            table_name: 表名过滤（可选）
            
        Returns:
            文件列表
        """
        if table_name:
            pattern = f"{table_name}_*.csv"
        else:
            pattern = "*.csv"
        
        files = list(self.samples_dir.glob(pattern))
        return [f.name for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)]
    
    def list_pending(self) -> List[str]:
        """列出所有待插入文件"""
        files = list(self.pending_dir.glob("*.csv"))
        return [f.name for f in files]