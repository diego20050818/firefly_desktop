import json
import time
import uuid
from typing import Any,Dict
from fastapi import APIRouter,HTTPException,WebSocket,WebSocketDisconnect
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 

from service.agent import ChatAgent
from service.llm_register import get_provider_class
from service.llm_service import ChatCompletionResponse

# ===================== 会话管理 =====================

# 存储活跃的 ChatAgent 会话（session_id -> ChatAgent）
active_agent_sessions: Dict[str, ChatAgent] = {}

# 存储活跃的基础 LLM 会话（session_id -> LLMService）
active_sessions: Dict[str, Any] = {}

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

agent_router = APIRouter(
    prefix='/agent',
    tags=['agent'],

)

@agent_router.post("/chat")
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


@agent_router.post("/reset")
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

@agent_router.post("/stream_chat")
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

@agent_router.websocket("/ws/chat")
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