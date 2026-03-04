"""
数据库操作类 - 封装 SQLite 数据库连接管理
"""

import sqlite3
import threading
from loguru import logger
from .sql_init import DB_PATH

class DatabaseManager:
    """数据库管理器 - 单例模式
    
    负责管理数据库连接，确保整个应用只有一个连接实例
    支持线程安全的连接访问
    """
    _instance = None
    _lock = threading.Lock()
    _connection = None

    def __new__(cls):
        """创建并返回对象实例，使用双重检查锁保证线程安全"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接
        
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        if self._connection is None:
            self._connection = sqlite3.connect(DB_PATH)
            self._connection.row_factory = sqlite3.Row  # 支持字典访问
        return self._connection
    
    def commit_tasks(self):
        if self._connection:
            self._connection.commit()

    def close_connection(self) -> bool:
        """关闭数据库连接
        
        Returns:
            bool: 是否成功关闭
        """
        try:
            if self._connection:
                self._connection.commit()
                self._connection.close()
                self._connection = None
            logger.success('close database success')
            return True

        except Exception as e:
            logger.error(f'failed to close database:{e}')
            return False

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