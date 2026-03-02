from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 

from tools.registry_tools import tool_registry

# ===================== 工具查询端点 =====================

tools_router = APIRouter(
    prefix='/tools',
    tags=['tools']
)
@tools_router.get("/available")
async def list_available_tools() -> dict:
    """列出所有可用的 MCP 工具（触发重新扫描）。"""
    tools = await tool_registry.get_all_tools()
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ]
    }

 # TODO 
@tools_router.get("/")
async def get_tools() -> dict:
    """获取所有可用工具列表。"""
    tools = await tool_registry.get_all_tools()
    return {"tools": [tool.dict() for tool in tools]}


@tools_router.get("/cached")
def get_cached_tools() -> dict:
    """获取缓存的工具列表（不触发重新扫描）。"""
    tools = tool_registry.get_cached_tools()
    return {"tools": [tool.dict() for tool in tools]}