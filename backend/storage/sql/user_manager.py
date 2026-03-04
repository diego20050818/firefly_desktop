"""
数据库操作类 - 封装所有 SQLite 数据库的 CRUD 操作
提供用户管理、对话历史、偏好设置等数据持久化功能
"""
import sqlite3
import json
import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from loguru import logger
from .sql_init import DB_PATH
from .database_manager import DatabaseManager

class UserManager:
    """用户管理器"""
    
    @staticmethod
    def create_user(user_id: str, nickname: Optional[str] = None, 
                   preferences: Optional[Dict] = None) -> bool:
        """创建新用户"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            preferences_json = json.dumps(preferences) if preferences else None
            
            cursor.execute("""
                INSERT INTO users (user_id, nickname, preferences)
                VALUES (?, ?, ?)
            """, (user_id, nickname, preferences_json))
            
            conn.commit()
            logger.info(f"用户 {user_id} 创建成功")
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"用户 {user_id} 已存在")
            return False
        except Exception as e:
            logger.error(f"创建用户失败：{e}")
            return False
    
    @staticmethod
    def get_user(user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM users WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.error(f"获取用户失败：{e}")
            return None
    
    @staticmethod
    def update_last_active(user_id: str):
        """更新用户最后活跃时间"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users 
                SET last_active_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            
            conn.commit()
        except Exception as e:
            logger.error(f"更新活跃时间失败：{e}")
    
    @staticmethod
    def update_preferences(user_id: str, preferences: Dict[str, Any]):
        """更新用户偏好设置"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            preferences_json = json.dumps(preferences)
            
            cursor.execute("""
                UPDATE users 
                SET preferences = ? 
                WHERE user_id = ?
            """, (preferences_json, user_id))
            
            conn.commit()
            logger.info(f"用户 {user_id} 偏好设置已更新")
        except Exception as e:
            logger.error(f"更新偏好设置失败：{e}")
