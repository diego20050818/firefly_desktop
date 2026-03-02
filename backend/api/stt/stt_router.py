from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 
import asyncio


from voice.stt import STTService

stt_router = APIRouter(
    prefix='/stt',
    tags=['stt']
)
# ===================== 设置全局变量 =====================
stt_service = STTService()

# ===================== stt 模型控制端点 =====================
@stt_router.post("/start")
async def start_stt():
    """开始录音并等待 VAD 结束"""
    global stt_service
    
    # 直接使用全局 stt_service 的 VAD 模式
    # 这将启动一个任务，并在完成后存储结果
    async def stt_task_wrstt_routerer():
        result = await stt_service.start_listening(mode="vad")
        start_stt.last_result = result
        logger.info(f"STT Task finished: {result}")

    start_stt.task = asyncio.create_task(stt_task_wrstt_routerer())
    start_stt.last_result = None
    
    return {
        "message": "语音识别已启动 (VAD)",
        "status": "listening"
    }


@stt_router.post("/stop")
async def stop_stt():
    """停止语音转文字并返回结果"""
    # 在 VAD 模式下，通常是等待任务自行结束
    # 如果强制停止，可以 cancel 任务
    if hasattr(start_stt, 'task') and not start_stt.task.done():
        # 我们这里不强制 cancel，而是等待一小会儿看是否已经有了结果
        # 或者在前端控制逻辑中，stop 只是为了获取结果
        pass
    
    result = getattr(start_stt, 'last_result', "")
    
    return {
        "transcription": result,
        "status": "stopped"
    }


@stt_router.post("/transcribe")
async def transcribe_audio(duration: int = 10):
    """录音指定时间并返回转录结果（使用全局服务，避免重载模型）"""
    result = await stt_service.start_listening(duration=duration, mode="continuous")
    
    return {
        "transcription": result,
        "duration": duration
    }


@stt_router.post("/transcribe_vad")
async def transcribe_audio_vad():
    """使用 VAD 智能检测说话和静默，捕获单次说话内容"""
    result = await stt_service.start_listening(mode="vad")
    
    return {
        "transcription": result,
        "mode": "vad"
    }


@stt_router.get("/status")
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
