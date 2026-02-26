"""FastAPI 应用主模块 - 提供 REST 和 WebSocket API。

该模块定义了所有 HTTP 和 WebSocket 端点:
- /agent/chat: 带自动工具调用的智能对话接口（推荐）
- /chat/{provider}: 基础 LLM 对话接口（无工具调用）
- /ws/agent/chat: WebSocket 智能对话（实时推送工具调用状态）
- /ws/chat/{provider}: WebSocket 基础对话
- /tools/*: 工具查询接口

编码规范: Google Python Style Guide
"""

import json
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from pydantic import BaseModel

from service.agent import ChatAgent
from service.llm_register import get_provider_class
from service.llm_service import ChatCompletionResponse
from tools.registry_tools import tool_registry
from voice.stt import STTService

# ===================== 设置全局变量 =====================
stt_service = STTService()

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
        
    except Exception as e:
        logger.error(f"MCP 初始化失败: {e}")

    yield

    # 关闭系统时清理连接
    try:
        from tools.stdio_mcp import stdio_mcp_manager
        logger.info("系统关闭：正在清理 MCP 服务器资源...")
        await stdio_mcp_manager.cleanup()
        
        # 停止STT服务
        if hasattr(start_stt, 'current_stt') and start_stt.current_stt:
            start_stt.current_stt.stop_listening()
            
    except Exception as e:
        logger.error(f"清理 MCP 资源失败: {e}")


app = FastAPI(
    title="Firefly AI Gateway",
    version="0.2.0",
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

# ===================== 会话管理 =====================

# 存储活跃的 ChatAgent 会话（session_id -> ChatAgent）
active_agent_sessions: Dict[str, ChatAgent] = {}

# 存储活跃的基础 LLM 会话（session_id -> LLMService）
active_sessions: Dict[str, Any] = {}


# ===================== 请求/响应模型 =====================

class AgentChatRequest(BaseModel):
    """Agent 对话请求模型。

    Attributes:
        prompt: 用户输入文本。
        session_id: 会话 ID（可选，用于维持多轮对话）。
        provider: LLM 提供商，默认 deepseek。
    """

    prompt: str
    session_id: str = "default"
    provider: str = "deepseek"


# ===================== 基础端点 =====================

@app.get("/")
async def read_root() -> dict:
    """根路径 - 返回服务信息。"""
    return {
        "message": "welcome to firefly api",
        "logo_url": "/static/logo.png",
        "docs_url": "/docs",
        "version": "0.2.0",
    }


@app.get("/health")
async def health_check() -> dict:
    """健康检查端点。"""
    return {"status": "ok"}


# ===================== Agent 智能对话端点 =====================

@app.post("/agent/chat")
async def agent_chat_endpoint(request: AgentChatRequest) -> dict:
    """带自动工具调用的智能对话接口（推荐使用）。

    该接口会自动:
    1. 将用户输入发送给 LLM
    2. 如果 LLM 请求调用工具，自动执行 MCP 工具
    3. 将工具结果反馈给 LLM
    4. 返回最终的 AI 回复

    Args:
        request: 包含 prompt、session_id、provider 的请求体。

    Returns:
        包含 AI 回复、工具调用历史和使用统计的响应。
    """
    session_id = request.session_id

    # 获取或创建 ChatAgent 会话
    if session_id not in active_agent_sessions:
        try:
            active_agent_sessions[session_id] = ChatAgent(
                provider=request.provider
            )
            logger.info(f"创建新的 Agent 会话: {session_id}")
        except Exception as e:
            logger.error(f"创建 Agent 会话失败: {e}")
            return {"error": str(e)}

    agent = active_agent_sessions[session_id]

    try:
        # 执行智能对话（自动处理工具调用）
        result = await agent.chat(request.prompt)
        return {
            "content": result["content"],
            "tool_calls_history": result["tool_calls_history"],
            "reasoning_content": result.get("reasoning_content"),
            "usage": result.get("usage", {}),
            "session_id": session_id,
        }
    except Exception as e:
        logger.error(f"Agent 对话处理失败: {e}")
        return {"error": str(e)}


@app.post("/agent/reset")
async def agent_reset_endpoint(session_id: str = "default") -> dict:
    """重置 Agent 会话历史。

    Args:
        session_id: 要重置的会话 ID。
    """
    if session_id in active_agent_sessions:
        active_agent_sessions[session_id].reset()
        return {"message": f"会话 {session_id} 已重置"}
    return {"message": f"会话 {session_id} 不存在"}


# ===================== 流式对话端点 =====================

@app.post("/agent/stream_chat")
async def agent_stream_chat_endpoint(request: AgentChatRequest):
    """流式智能对话接口（SSE - Server-Sent Events）。

    通过 HTTP SSE 流式推送 token 和工具调用状态。
    支持多轮对话（通过 session_id 维持上下文）。

    每个 SSE 事件格式:
        data: {"type": "token", "content": "你"}
        data: {"type": "reasoning", "content": "让我想想..."}
        data: {"type": "tool_start", "tool_name": "add", "arguments": "..."}
        data: {"type": "tool_end", "tool_name": "add", "result": "42"}
        data: {"type": "done", "full_content": "...", "tool_calls_history": [...]}

    Args:
        request: 包含 prompt、session_id、provider 的请求体。

    Returns:
        StreamingResponse（text/event-stream）。
    """
    from starlette.responses import StreamingResponse

    session_id = request.session_id

    # 获取或创建 ChatAgent 会话
    if session_id not in active_agent_sessions:
        try:
            active_agent_sessions[session_id] = ChatAgent(
                provider=request.provider
            )
            logger.info(f"创建新的 Agent 流式会话: {session_id}")
        except Exception as e:
            logger.error(f"创建 Agent 会话失败: {e}")

            async def error_gen():
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                error_gen(), media_type="text/event-stream"
            )

    agent = active_agent_sessions[session_id]

    async def event_generator():
        """SSE 事件生成器。"""
        try:
            async for event in agent.stream_chat(request.prompt):
                # 每个事件作为 SSE data 行发送
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式对话异常: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===================== WebSocket Agent 对话（流式） =====================

@app.websocket("/ws/agent/chat")
async def websocket_agent_chat(websocket: WebSocket) -> None:
    """WebSocket 流式智能对话端点。

    支持多轮对话和逐 token 推送。

    消息协议 (JSON):
    客户端发送:
        {"type": "user_input", "data": {"text": "..."}, "provider": "deepseek"}

    服务端逐 token 推送:
        {"type": "token", "content": "你"}
        {"type": "reasoning", "content": "..."}
        {"type": "tool_start", "tool_name": "add", "arguments": "..."}
        {"type": "tool_end", "tool_name": "add", "result": "42"}
        {"type": "done", "full_content": "...", "tool_calls_history": [...]}
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    agent: ChatAgent | None = None

    logger.info(f"WebSocket Agent 连接建立: {session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "user_input":
                user_text = data.get("data", {}).get("text", "")
                provider = data.get("provider", "deepseek")

                # 初始化 Agent（首次消息时，后续复用实现多轮对话）
                if agent is None:
                    agent = ChatAgent(provider=provider)

                # 流式推送每个事件
                async for event in agent.stream_chat(user_text):
                    await websocket.send_json(event)

            elif msg_type == "reset":
                # 支持客户端主动重置对话
                if agent is not None:
                    agent.reset()
                    await websocket.send_json({
                        "type": "system",
                        "message": "对话已重置",
                    })

            elif msg_type == "heartbeat":
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket Agent 连接断开: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket Agent 异常: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass


# ===================== 基础 LLM 对话端点（保留兼容） =====================

@app.post("/chat/{provider}")
async def chat_endpoint(
    provider: str,
    request: Dict[str, Any],
) -> dict:
    """基础 LLM 对话接口（无自动工具调用）。

    Args:
        provider: LLM 提供商名称。
        request: 包含 prompt 和 session_id 的请求体。
    """
    user_prompt = request.get("prompt", "")
    session_id = request.get("session_id", "default")

    if session_id not in active_sessions:
        provider_cls = get_provider_class(provider)
        active_sessions[session_id] = provider_cls()

    client = active_sessions[session_id]
    response: ChatCompletionResponse = await client.chat_completion(
        user_prompt
    )

    return {
        "content": response.content,
        "tool_calls": response.tool_calls,
        "usage": response.usage,
    }


@app.websocket("/ws/chat/{provider}")
async def websocket_chat(websocket: WebSocket, provider: str) -> None:
    """基础 WebSocket 对话（无自动工具调用）。

    Args:
        websocket: WebSocket 连接。
        provider: LLM 提供商名称。
    """
    await websocket.accept()

    provider_cls = get_provider_class(provider)
    client = provider_cls()

    while True:
        try:
            data = await websocket.receive_json()
            user_prompt = data.get("prompt", "")

            response: ChatCompletionResponse | None = (
                await client.chat_completion(user_prompt)
            )

            if response is None:
                logger.warning("LLM 返回空响应")
                continue

            await websocket.send_json({
                "type": "response",
                "content": response.content,
                "tool_calls": response.tool_calls,
                "finish_reason": response.finish_reason,
            })
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
            break


# ===================== 工具查询端点 =====================

@app.get("/tools/available")
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


@app.get("/tools")
async def get_tools() -> dict:
    """获取所有可用工具列表。"""
    tools = await tool_registry.get_all_tools()
    return {"tools": [tool.dict() for tool in tools]}


@app.get("/tools/cached")
def get_cached_tools() -> dict:
    """获取缓存的工具列表（不触发重新扫描）。"""
    tools = tool_registry.get_cached_tools()
    return {"tools": [tool.dict() for tool in tools]}

@app.post("/stt/start")
async def start_stt():
    """开始语音转文字"""
    global stt_service
    
    # 创建新的STT服务实例，避免并发问题
    if hasattr(start_stt, 'current_stt') and start_stt.current_stt:
        start_stt.current_stt.stop_listening()
    
    start_stt.current_stt = STTService()
    transcription_task = asyncio.create_task(start_stt.current_stt.start_listening())
    
    # 保存任务引用以便稍后访问
    start_stt.task = transcription_task
    
    return {
        "message": "语音识别已开始",
        "status": "listening"
    }


@app.post("/stt/stop")
async def stop_stt():
    """停止语音转文字并返回结果"""
    global stt_service
    
    if hasattr(start_stt, 'current_stt') and start_stt.current_stt:
        start_stt.current_stt.stop_listening()
        
        # 等待转录完成
        result = start_stt.current_stt.get_transcription_result()
        
        return {
            "transcription": result,
            "status": "stopped"
        }
    
    return {
        "message": "没有活动的语音识别会话",
        "status": "none"
    }


@app.post("/stt/transcribe")
async def transcribe_audio(duration: int = 10):
    """录音指定时间并返回转录结果（使用全局服务，避免重载模型）"""
    result = await stt_service.start_listening(duration=duration, mode="continuous")
    
    return {
        "transcription": result,
        "duration": duration
    }


@app.post("/stt/transcribe_vad")
async def transcribe_audio_vad():
    """使用 VAD 智能检测说话和静默，捕获单次说话内容"""
    result = await stt_service.start_listening(mode="vad")
    
    return {
        "transcription": result,
        "mode": "vad"
    }


@app.get("/stt/status")
async def get_stt_status():
    """获取当前STT服务状态"""
    # 这里需要根据实际情况判断是否正在监听
    is_active = False
    if hasattr(start_stt, 'current_stt'):
        is_active = getattr(start_stt.current_stt, 'listening_active', False)
    
    return {
        "status": "active" if is_active else "inactive",
        "is_active": is_active
    }