import asyncio
from loguru import logger
import uvicorn
import os
import subprocess

from service.llm_register import get_provider_class
from api.app import app
from tools.launch_app import mcp
from tools.registry_tools import tool_registry
from voice.tts_service import tts_service
from storage.sql import init_db_table
from tools.config_manager import ConfigManager

async def run_fastapi():
    """运行FastAPI服务"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def run_fastmcp():
    """运行FastMCP服务"""
    # FastMCP的run_async方法不接受host和port参数，它使用标准IO协议
    await mcp.run_async()

async def load_tts_models():
    """预加载TTS模型"""
    logger.info("Starting TTS service...")
    tts_service.start_server()
    
    logger.info("Initializing TTS character...")
    success = await tts_service.initialize_character()
    if success:
        logger.success("TTS models loaded successfully")
    else:
        logger.error("Failed to load TTS models")

@logger.catch()
async def main():
    # 初始化数据库表
    logger.info("Initializing database...")
    try:
        init_db_table()
        logger.success("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # 启动配置管理器
    logger.info("Starting configuration manager...")
    config_manager = ConfigManager()
    config_manager.start_watching(interval=5.0)  # 每 5 秒检查一次配置变化
    logger.success("Configuration manager started")
    
    # 预加载 TTS 模型
    await load_tts_models()
    
    # 并发运行两个服务
    await asyncio.gather(
        run_fastapi(), # 运行 fastapi
        run_fastmcp(), # 运行 mcp
    )

if __name__ == "__main__":
    if not os.getcwd().endswith('backend'):
        logger.error(f"you should cd into /backend subdir to cdrun it,current path:{os.getcwd()}")
        raise
    else:
        logger.info(f"current path:{os.getcwd()}")
    
    # 使用 asyncio.run 启动主程序
    asyncio.run(main())