import asyncio
from loguru import logger
import uvicorn
import os
import subprocess

from service.llm_register import get_provider_class
from api.app import app

from tools.launch_app import mcp
from tools.registry_tools import tool_registry

async def run_fastapi():
    """运行FastAPI服务"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def run_fastmcp():
    """运行FastMCP服务"""
    # FastMCP的run_async方法不接受host和port参数，它使用标准IO协议
    await mcp.run_async()


@logger.catch()
async def main():
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

    