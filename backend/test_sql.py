
"""
数据库使用示例
演示如何在实际项目中使用数据库模块
"""
from storage.sql import (
    UserManager,
    ConversationManager,
    PreferenceManager,
    ToolUsageManager,
    init_db_table,
    DatabaseManager,
    clear_database
)
from loguru import logger


def test_database():
    """测试数据库功能"""
    
    # 1. 初始化数据库
    logger.info("=== 初始化数据库 ===")
    init_db_table()

    DatabaseManager.get_connection
    
    # 2. 创建用户
    logger.info("\n=== 创建用户 ===")
    user_id = "test_user_001"
    UserManager.create_user(
        user_id=user_id,
        nickname="测试用户",
        preferences={"theme": "dark", "language": "zh-CN"}
    )
    
    # 3. 获取用户信息
    logger.info("\n=== 获取用户信息 ===")
    user = UserManager.get_user(user_id)
    if user:
        logger.info(f"用户信息：{dict(user)}")
    
    # 4. 更新活跃时间
    logger.info("\n=== 更新活跃时间 ===")
    UserManager.update_last_active(user_id)
    
    # 5. 设置偏好
    logger.info("\n=== 设置偏好 ===")
    PreferenceManager.set_preference(
        user_id=user_id,
        category="chat_style",
        key="formality",
        value="casual",
        confidence=0.9
    )
    
    # 6. 获取偏好
    logger.info("\n=== 获取偏好 ===")
    preference = PreferenceManager.get_preference(
        user_id=user_id,
        category="chat_style",
        key="formality"
    )
    logger.info(f"偏好设置：{preference}")
    
    # 7. 保存对话
    logger.info("\n=== 保存对话 ===")
    session_id = "session_20240303_001"
    
    # 用户消息
    ConversationManager.save_message(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content="你好，请介绍一下你自己"
    )
    
    # 助手回复
    ConversationManager.save_message(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content="你好！我是 Firefly 智能助手...",
        reasoning_content="用户想要了解我的基本信息",
        usage={"prompt_tokens": 10, "total_tokens": 50}
    )
    
    # 8. 获取对话历史
    logger.info("\n=== 获取对话历史 ===")
    history = ConversationManager.get_session_history(session_id)
    for msg in history:
        logger.info(f"[{msg['role']}] {msg['content']}")
    
    # 9. 记录工具使用
    logger.info("\n=== 记录工具使用 ===")
    ToolUsageManager.log_tool_usage(
        session_id=session_id,
        tool_name="search_web",
        arguments={"query": "天气"},
        result="北京今天晴朗，25°C",
        duration_ms=150,
        success=True
    )
    
    # 10. 获取工具使用统计
    logger.info("\n=== 工具使用统计 ===")
    stats = ToolUsageManager.get_usage_stats(session_id)
    logger.info(f"统计信息：{stats}")
    
    clear_database()

    logger.success("\n=== 所有测试完成 ===")
    DatabaseManager.close_connection


if __name__ == "__main__":
    test_database()