"""
数据库操作类 - 封装 SQLite 数据库连接管理
"""

import sqlite3
import threading
from loguru import logger
from .sql_init import DB_PATH


class DatabaseManager:
    """数据库管理器 - 单例模式，支持线程安全的连接访问
    
    负责管理数据库连接，每个线程都有自己的连接实例
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """创建并返回对象实例，使用双重检查锁保证线程安全"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化线程本地存储"""
        self._local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接
        
        Returns:
            sqlite3.Connection: 当前线程的数据库连接对象
        """
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(DB_PATH)
            self._local.connection.row_factory = sqlite3.Row  # 支持字典访问
        return self._local.connection

    def close_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

    def commit(self):
        """提交当前线程的事务"""
        if hasattr(self._local, 'connection'):
            self._local.connection.commit()

    def rollback(self):
        """回滚当前线程的事务"""
        if hasattr(self._local, 'connection'):
            self._local.connection.rollback()

def clear_database(keep_users: bool = False):
    """清空数据库
    
    Args:
        keep_users: 是否保留用户数据
    """
    try:
        conn = DatabaseManager().get_connection()
        cursor = conn.cursor()
        
        if keep_users:
            # 只清空业务数据
            cursor.execute("DELETE FROM tool_usage_logs")
            cursor.execute("DELETE FROM conversations_history")
            cursor.execute("DELETE FROM user_preferences")
            cursor.execute("DELETE FROM memory_weights")
            logger.info("已清空业务数据，保留用户信息")
        else:
            # 清空所有表
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM tool_usage_logs")
            cursor.execute("DELETE FROM conversations_history")
            cursor.execute("DELETE FROM user_preferences")
            cursor.execute("DELETE FROM memory_weights")
            
            # 重置自增 ID
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='users'")
            logger.info("已清空所有数据并重置自增 ID")
        
        conn.commit()
        logger.success("数据库清理完成")
        
    except Exception as e:
        logger.error(f"清理数据库失败：{e}")
        raise