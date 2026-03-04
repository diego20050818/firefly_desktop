from pathlib import Path
import sqlite3
import datetime

from loguru import logger

DB_PATH = Path(__file__).parent / 'db' / 'user_data.db'

create_table_order = {
    "users": # 用户信息表
    """
    CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    nickname TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP,
    preferences JSON
    )
    """,

    "conversations_history": # 对话历史表
    """
    CREATE TABLE IF NOT EXISTS conversations_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT,
    role TEXT,
    content TEXT,
    tool_calls JSON,
    reasoning_content TEXT,
    usage JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
    """,

    "user_preferences":  # 用户偏好表
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    category TEXT,
    key TEXT,
    value TEXT,
    confidence REAL DEFAULT 1.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
    """,

    "tool_usage_logs":
    """
    CREATE TABLE IF NOT EXISTS tool_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT,
    arguments JSON,
    result TEXT,
    duration_ms INTEGER,
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    "memory_weights":
    """
    CREATE TABLE IF NOT EXISTS memory_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT,
    weight REAL DEFAULT 1.0,
    decay_rate REAL DEFAULT 0.1,
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 1
    );
    """
}

def init_db_table():
    """
    初始化数据库表，如果表已存在则跳过创建
    支持幂等操作，可多次调用而不会报错
    """
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        logger.info(f"开始初始化数据库：{DB_PATH}")
        
        for table_name, create_sql in create_table_order.items():
            try:
                cursor.execute(create_sql)
                conn.commit()
                logger.info(f"数据表 '{table_name}' 初始化完成（已存在则跳过）")
            except sqlite3.Error as e:
                logger.error(f"创建表 {table_name} 时出错：{e}")
                raise
        
        logger.success("数据库表初始化完成")
        
    except sqlite3.Error as e:
        logger.error(f"数据库连接错误：{e}")
        raise
    except Exception as e:
        logger.error(f"初始化过程中发生错误：{e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()
            logger.debug("数据库连接已关闭")


if __name__ == "__main__":
    init_db_table()
    print("数据库初始化完成！")