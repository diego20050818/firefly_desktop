import sqlite3
import json
from typing import Optional, List, Dict, Any
from loguru import logger

from .database_manager import DatabaseManager


class ConversationManager:
    """对话历史管理器"""
    
    @staticmethod
    def save_message(session_id: str, user_id: str, role: str, 
                    content: str, tool_calls: Optional[List] = None,
                    reasoning_content: Optional[str] = None,
                    usage: Optional[Dict] = None) -> bool:
        """保存对话消息"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            tool_calls_json = json.dumps(tool_calls) if tool_calls else None
            usage_json = json.dumps(usage) if usage else None
            
            cursor.execute("""
                INSERT INTO conversations_history 
                (session_id, user_id, role, content, tool_calls, 
                 reasoning_content, usage)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, role, content, tool_calls_json,
                  reasoning_content, usage_json))
            
            conn.commit()
            logger.debug(f"会话 {session_id} 消息已保存 ({role})")
            return True
            
        except Exception as e:
            logger.error(f"保存对话失败：{e}")
            return False
    
    @staticmethod
    def get_session_history(session_id: str, 
                           limit: int = 50) -> List[Dict[str, Any]]:
        """获取会话历史"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM conversations_history 
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (session_id, limit))
            
            rows = cursor.fetchall()
            messages = []
            for row in reversed(rows):  # 按时间正序返回
                msg_dict = dict(row)
                # 解析 JSON 字段
                if msg_dict.get('tool_calls'):
                    msg_dict['tool_calls'] = json.loads(msg_dict['tool_calls'])
                if msg_dict.get('usage'):
                    msg_dict['usage'] = json.loads(msg_dict['usage'])
                messages.append(msg_dict)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取会话历史失败：{e}")
            return []
    
    @staticmethod
    def clear_session(session_id: str):
        """清空会话历史"""
        try:
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM conversations_history 
                WHERE session_id = ?
            """, (session_id,))
            
            conn.commit()
            logger.info(f"会话 {session_id} 已清空")
        except Exception as e:
            logger.error(f"清空会话失败：{e}")