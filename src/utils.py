"""
工具函数模块
============
通用工具函数
"""

import os
from datetime import datetime
from loguru import logger
import sys

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


def setup_logging(log_file: str = None):
    """配置日志"""
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")
    if log_file:
        logger.add(log_file, level="DEBUG", rotation="10 MB")
    logger.info("日志系统已初始化")


def get_timestamp() -> str:
    """获取时间戳字符串"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(directory: str):
    """确保目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.debug(f"创建目录: {directory}")


def format_bytes(bytes_num: int) -> str:
    """格式化字节数"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} TB"