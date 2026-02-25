# api/app.py
from fastapi import FastAPI, WebSocket, Depends,Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from loguru import logger
import asyncio
import base64
import os

from service.llm_register import get_provider_class
from service.llm_service import ChatMessage, ChatCompletionResponse
from tools.registry_tools import tool_registry


app = FastAPI(title="Firefly AI Gateway", version="0.1.0")

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 会话管理
active_sessions: Dict[str, Any] = {}

@app.get("/")
async def read_root():
    return {
        "message": "welcome to firefly api",
        "logo_url": "/static/logo.png",  # 图片URL
        "docs_url": "/docs",
        "version": "0.1.0"
    }

# 添加静态文件服务
from fastapi.staticfiles import StaticFiles
import os

# 确保 static 目录存在
os.makedirs("static", exist_ok=True)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/chat/{provider}")
async def chat_endpoint(
    provider: str,
    request: Dict[str, Any]
):
    """同步聊天接口"""
    user_prompt = request.get("prompt", "")
    session_id = request.get("session_id", "default")
    
    if session_id not in active_sessions:
        provider_cls = get_provider_class(provider)
        active_sessions[session_id] = provider_cls()
    
    client = active_sessions[session_id]
    response: ChatCompletionResponse = await client.chat_completion(user_prompt)
    
    return {
        "content": response.content,
        "tool_calls": response.tool_calls,
        "usage": response.usage
    }

@app.websocket("/ws/chat/{provider}")
async def websocket_chat(websocket: WebSocket, provider: str):
    """WebSocket 实时聊天"""
    await websocket.accept()
    
    provider_cls = get_provider_class(provider)
    client = provider_cls()
    
    while True:
        try:
            data = await websocket.receive_json()
            user_prompt = data.get("prompt", "")
            
            response: ChatCompletionResponse | None = await client.chat_completion(user_prompt)
            
            if response is None:
                logger.warning("respons is None")

            await websocket.send_json({
                "type": "response",
                "content": response.content,
                "tool_calls": response.tool_calls,
                "finish_reason": response.finish_reason
            })
        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            break

@app.get("/tools/available")
async def list_available_tools():
    """列出所有可用工具（从 MCP 服务器获取）"""
    tools = await tool_registry.get_all_tools()
    return {
        "tools":[
            {
            "name":tool.name,
            "description":tool.description,
            "parameters":tool.parameters
            }
            for tool in tools
        ]
    }


@app.get("/tools")
async def get_tools():
    """获取所有可用工具列表"""
    tools = await tool_registry.get_all_tools()
    return {"tools": [tool.dict() for tool in tools]}

@app.get("/tools/cached")
def get_cached_tools():
    """获取缓存的工具列表"""
    tools = tool_registry.get_cached_tools()
    return {"tools": [tool.dict() for tool in tools]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)