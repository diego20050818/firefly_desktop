import sqlite3
import json
from typing import Optional, List, Dict, Any
from loguru import logger
from datetime import datetime
from .database_manager import DatabaseManager


def get_db_connection():
    """获取数据库连接的辅助函数"""
    return DatabaseManager().get_connection()


class ConversationManager:
    """对话历史管理器"""
    
    @staticmethod
    def save_message(session_id: str, user_id: str, role: str, content: str, 
                    tool_calls=None, reasoning_content=None, usage=None):
        """保存消息到数据库"""
        try:
            # 将 ToolCall 对象转换为 JSON 序列化的格式
            serialized_tool_calls = None
            if tool_calls:
                if isinstance(tool_calls, list):
                    serialized_tool_calls = []
                    for tc in tool_calls:
                        if hasattr(tc, '__dict__'):  # ToolCall 对象
                            tc_dict = {
                                "id": getattr(tc, 'id', ''),
                                "type": getattr(tc, 'type', 'function'),
                                "function": getattr(tc, 'function', {})
                            }
                            serialized_tool_calls.append(tc_dict)
                        elif isinstance(tc, dict):  # 已经是字典格式
                            serialized_tool_calls.append(tc)
            
            # 创建消息对象
            message_data = {
                'session_id': session_id,
                'user_id': user_id,
                'role': role,
                'content': content,
                'tool_calls': json.dumps(serialized_tool_calls) if serialized_tool_calls else None,
                'reasoning_content': reasoning_content,
                'usage': json.dumps(usage) if usage else None,  # 添加用量信息
                'timestamp': datetime.now()
            }
            
            # 保存到数据库
            conn = DatabaseManager().get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations_history 
                (session_id, user_id, role, content, tool_calls, reasoning_content, usage, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_data['session_id'],
                message_data['user_id'],
                message_data['role'],
                message_data['content'],
                message_data['tool_calls'],
                message_data['reasoning_content'],
                message_data['usage'],
                message_data['timestamp']
            ))
            conn.commit()
                
            logger.debug(f"会话 {session_id} 消息已保存 ({role})")
            
        except Exception as e:
            logger.error(f"保存对话失败：{e}")
            raise
    
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
                ORDER BY created_at ASC
                LIMIT ?
            """, (session_id, limit))
            
            rows = cursor.fetchall()
            messages = []
            for row in rows:  # 已按时间顺序排列
                msg_dict = dict(row)
                # 解析 JSON 字段
                if msg_dict.get('tool_calls'):
                    try:
                        msg_dict['tool_calls'] = json.loads(msg_dict['tool_calls'])
                    except (json.JSONDecodeError, TypeError):
                        msg_dict['tool_calls'] = None
                if msg_dict.get('usage'):
                    try:
                        msg_dict['usage'] = json.loads(msg_dict['usage'])
                    except (json.JSONDecodeError, TypeError):
                        msg_dict['usage'] = None
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