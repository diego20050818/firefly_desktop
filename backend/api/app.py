"""FastAPI 应用主模块 - 提供 REST 和 WebSocket API。

该模块定义了所有 HTTP 和 WebSocket 端点:
- /agent/chat: 带自动工具调用的智能对话接口（推荐）
- /chat/{provider}: 基础 LLM 对话接口（无工具调用）
- /ws/agent/chat: WebSocket 智能对话（实时推送工具调用状态）
- /ws/chat/{provider}: WebSocket 基础对话
- /tools/*: 工具查询接口

编码规范: Google Python Style Guide
"""


from typing import Any, Dict
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from pydantic import BaseModel

from api.settings.setting_router import settingRouter
from api.agent.agent_router import agent_router
from api.tools.tools_router import tools_router
from api.stt.stt_router import stt_router
from api.tts.tts_router import tts_router

from tools.registry_tools import tool_registry
from voice.tts_service import tts_service


# ===================== 设置全局变量 =====================
# stt_service = STTService()

# ===================== 应用初始化 =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理器，在启动时初始化 MCP 环境。"""
    try:
        from tools.stdio_mcp import stdio_mcp_manager
        
        logger.info("系统启动：正在初始化 Stdio MCP 服务器...")
        await stdio_mcp_manager.initialize()

        logger.info("系统启动：正在刷新全局工具注册表...")
        await tool_registry.get_all_tools()
        
        # 初始化STT服务
        logger.info("系统启动：正在初始化 STT 服务...")
        
        # 核心修复：初始化 TTS 服务
        logger.info("系统启动：正在连接并初始化 TTS 服务...")
        if tts_service.connect_to_existing_server():
            await tts_service.initialize_character()
            await tts_service.enable_tts()
            logger.info("TTS 服务初始化完成并已启用。")
        else:
            logger.error("无法连接到 TTS 服务器，请检查 main.py 是否已启动。")
            
    except Exception as e:
        logger.error(f"系统初始化过程中发生错误: {e}")

    yield

    # 关闭系统时清理连接
    try:
        from tools.stdio_mcp import stdio_mcp_manager
        logger.info("系统关闭：正在清理 MCP 服务器资源...")
        await stdio_mcp_manager.cleanup()
        
        # # 停止STT服务
        # if hasattr(start_stt, 'current_stt') and start_stt.current_stt:
        #     start_stt.current_stt.stop_listening()
            
    except Exception as e:
        logger.error(f"清理 MCP 资源失败: {e}")


app = FastAPI(
    title="Firefly AI Gateway",
    version="0.0.1",
    description="AI 桌宠后端 - 支持 MCP 工具调用的智能对话网关",
    lifespan=lifespan,
)

# CORS 配置（开发环境允许所有来源，生产环境需限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保静态文件目录存在并挂载
import os

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===================== 导入子router =====================
app.include_router(settingRouter)
app.include_router(agent_router)
app.include_router(tools_router)
app.include_router(stt_router)
app.include_router(tts_router)

# ===================== 基础端点 =====================

@app.get("/")
async def read_root() -> dict:
    """根路径 - 返回服务信息。"""
    return {
        "message": "welcome to firefly api",
        "logo_url": "/static/logo.png",
        "docs_url": "/docs",
        "version": "0.0.1",
    }


@app.get("/health")
async def health_check() -> dict:
    """健康检查端点。"""
    return {"status": "ok"}



@app.get("/emoji/list")
def list_emojis():
    try:
        import os
        folder = "./static/emoji"
        logger.info(f"Listing emojis from {folder}")
        return [f for f in os.listdir(folder) if f.endswith(".png")]
    except Exception as e:
        logger.error(f"Failed to list emojis: {e}")
        return []