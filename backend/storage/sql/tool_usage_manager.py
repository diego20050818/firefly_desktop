import sqlite3
import json
import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from loguru import logger
from .sql_init import DB_PATH
from .database_manager import DatabaseManager

class ToolUsageManager:
    """工具使用记录管理器"""

    @staticmethod
    def log_tool_usage(session_id: str, tool_name: str,
                       arguments: Dict, result: str,
                       duration_ms: int, success: bool):
        """记录工具使用情况"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()

            arguments_json = json.dumps(arguments)

            cursor.execute("""
                INSERT INTO tool_usage_logs 
                (session_id, tool_name, arguments, result, 
                 duration_ms, success)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, tool_name, arguments_json,
                  result, duration_ms, success))

            conn.commit()
        except Exception as e:
            logger.error(f"记录工具使用失败：{e}")

    @staticmethod
    def get_usage_stats(session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取工具使用统计"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()

            if session_id:
                cursor.execute("""
                    SELECT tool_name, COUNT(*) as count,
                           AVG(duration_ms) as avg_duration,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate
                    FROM tool_usage_logs
                    WHERE session_id = ?
                    GROUP BY tool_name
                """, (session_id,))
            else:
                cursor.execute("""
                    SELECT tool_name, COUNT(*) as count,
                           AVG(duration_ms) as avg_duration,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate
                    FROM tool_usage_logs
                    GROUP BY tool_name
                """)

            rows = cursor.fetchall()
            stats = {}
            for row in rows:
                stats[row['tool_name']] = {
                    'count': row['count'],
                    'avg_duration_ms': row['avg_duration'],
                    'success_rate': row['success_rate']
                }

            return stats

        except Exception as e:
            logger.error(f"获取使用统计失败：{e}")
            return {}
