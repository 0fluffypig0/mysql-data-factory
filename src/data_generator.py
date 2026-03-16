"""
数据生成模块
============
使用Faker生成测试数据，支持从样本记录学习并生成相似数据
"""

from faker import Faker
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import random
import pandas as pd
from loguru import logger
import sys

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


class DataGenerator:
    """
    测试数据生成器
    
    用法:
        # 方式1: 生成随机数据
        generator = DataGenerator(locale='ja_JP')
        data = generator.generate_legal_data(count=100)
        
        # 方式2: 从样本生成
        sample_df = pd.read_csv('sample.csv')
        data = generator.generate_from_sample(sample_df, count=1000)
    """
    
    def __init__(self, locale: str = 'ja_JP'):
        """
        初始化生成器
        
        Args:
            locale: Faker语言环境（默认日语）
        """
        self.fake = Faker(locale)
        self.locale = locale
        logger.info(f"初始化数据生成器: {locale}")
    
    def generate_legal_data(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        生成法人数据
        
        Args:
            count: 生成数量
            
        Returns:
            数据列表
        """
        logger.info(f"生成 {count} 条法人数据")
        return [self._generate_one_legal_data() for _ in range(count)]
    
    def _generate_one_legal_data(self) -> Dict[str, Any]:
        """生成单条法人数据"""
        return {
            'LEGAL_ID': self.fake.unique.random_int(min=10000, max=99999),
            'USER_ID': self.fake.unique.random_int(min=100000, max=999999),
            'COMPANY_ID': self.fake.random_int(min=10000, max=99999),
            'COMPANY_FROM_INDI': self.fake.random_int(min=0, max=1),
            'COMPANY_FROM_CODE': self.fake.random_int(min=1, max=99),
            'LEGAL_NAME': self.fake.company(),
            'LEGAL_NAME_KANA': self.fake.kana_name() if hasattr(self.fake, 'kana_name') else self.fake.company(),
            'LEGAL_NAME_EN': self.fake.company().upper(),
            'POSTAL_CODE': self.fake.postalcode(),
            'ADDRESS': self.fake.address(),
            'PHONE': self.fake.phone_number(),
            'EMAIL': self.fake.company_email(),
            'CREATED_AT': datetime.now(),
            'UPDATED_AT': datetime.now()
        }
    
    def generate_batch_job(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        生成批处理作业数据
        
        Args:
            count: 生成数量
            
        Returns:
            数据列表
        """
        logger.info(f"生成 {count} 条批处理数据")
        return [self._generate_one_batch_job() for _ in range(count)]
    
    def _generate_one_batch_job(self) -> Dict[str, Any]:
        """生成单条批处理数据"""
        return {
            'JOB_NAME': self.fake.word().upper() + '_JOB',
            'JOB_TYPE': random.choice(['DATA_IMPORT', 'DATA_EXPORT', 'REPORT', 'CLEANUP']),
            'SCHEDULE': random.choice(['daily', 'weekly', 'monthly']),
            'STATUS': random.choice(['PENDING', 'RUNNING', 'COMPLETED', 'FAILED']),
            'PRIORITY': random.randint(1, 10),
            'CREATED_AT': self.fake.date_time_between(start_date='-1y', end_date='now'),
            'UPDATED_AT': datetime.now()
        }
    
    def generate_from_sample(self, sample_df: pd.DataFrame, count: int, 
                            primary_key_col: str = None) -> pd.DataFrame:
        """
        从样本记录生成相似数据
        
        Args:
            sample_df: 样本DataFrame（通常1条记录）
            count: 生成数量
            primary_key_col: 主键列名（会自动递增）
            
        Returns:
            生成的DataFrame
        """
        if sample_df.empty:
            raise ValueError("样本数据为空")
        
        # 取第一条记录作为模板
        template = sample_df.iloc[0].to_dict()
        logger.info(f"从样本生成 {count} 条数据，模板主键: {primary_key_col}")
        
        generated_records = []
        
        for i in range(count):
            record = template.copy()
            
            # 递增主键（如果指定）
            if primary_key_col and primary_key_col in record:
                if isinstance(record[primary_key_col], (int, float)):
                    record[primary_key_col] = record[primary_key_col] + i
                else:
                    record[primary_key_col] = f"{record[primary_key_col]}_{i}"
            
            # 更新一些字段以产生变化
            if 'EMAIL' in record:
                record['EMAIL'] = self.fake.company_email()
            if 'UPDATED_AT' in record:
                record['UPDATED_AT'] = datetime.now()
            
            generated_records.append(record)
        
        return pd.DataFrame(generated_records)
    
    def generate_custom(self, count: int, field_generators: Dict[str, callable]) -> List[Dict[str, Any]]:
        """
        自定义生成数据
        
        Args:
            count: 生成数量
            field_generators: 字段生成器字典 {字段名: 生成函数}
            
        Returns:
            数据列表
        """
        logger.info(f"使用自定义生成器生成 {count} 条数据")
        records = []
        
        for _ in range(count):
            record = {}
            for field, generator in field_generators.items():
                record[field] = generator()
            records.append(record)
        
        return records
    
    def to_dataframe(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        将数据列表转换为DataFrame
        
        Args:
            data: 数据列表
            
        Returns:
            DataFrame
        """
        return pd.DataFrame(data)
    
    def save_to_csv(self, data: List[Dict[str, Any]], filepath: str):
        """
        保存为CSV文件
        
        Args:
            data: 数据列表
            filepath: 文件路径
        """
        df = self.to_dataframe(data)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.success(f"数据已保存到: {filepath}")