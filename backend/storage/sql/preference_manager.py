import sqlite3
import json
import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from loguru import logger
from .sql_init import DB_PATH
from .database_manager import DatabaseManager

class PreferenceManager:
    """用户偏好管理器"""

    @staticmethod
    def set_preference(user_id: str, category: str,
                       key: str, value: str, confidence: float = 1.0):
        """设置用户偏好"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences 
                (user_id, category, key, value, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, category, key, value, confidence))

            conn.commit()
            logger.debug(f"用户 {user_id} 偏好 {category}.{key} 已设置")
        except Exception as e:
            logger.error(f"设置偏好失败：{e}")

    @staticmethod
    def get_preference(user_id: str, category: str,
                       key: str) -> Optional[str]:
        """获取用户偏好"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT value FROM user_preferences 
                WHERE user_id = ? AND category = ? AND key = ?
            """, (user_id, category, key))

            row = cursor.fetchone()
            return row['value'] if row else None

        except Exception as e:
            logger.error(f"获取偏好失败：{e}")
            return None

    @staticmethod
    def get_all_preferences(user_id: str,
                            category: Optional[str] = None) -> Dict[str, str]:
        """获取所有偏好设置"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()

            if category:
                cursor.execute("""
                    SELECT category, key, value FROM user_preferences 
                    WHERE user_id = ? AND category = ?
                """, (user_id, category))
            else:
                cursor.execute("""
                    SELECT category, key, value FROM user_preferences 
                    WHERE user_id = ?
                """, (user_id,))

            rows = cursor.fetchall()
            preferences = {}
            for row in rows:
                pref_key = f"{row['category']}.{row['key']}"
                preferences[pref_key] = row['value']

            return preferences

        except Exception as e:
            logger.error(f"获取所有偏好失败：{e}")
            return {}
