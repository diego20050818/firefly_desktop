from typing import Any,Dict
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 

from voice.tts_service import tts_service

tts_router = APIRouter(
    prefix='/tts',
    tags=['tts']
)

class requestFormatted(BaseModel):
    text:str
    character_name:str = '流萤'
# ===================== tts 模型控制端点 =====================
@tts_router.post("/enable")
async def enable_tts():
    """启用TTS"""
    success = await tts_service.enable_tts()
    if success:
        return {"success": True, "message": "TTS enabled"}
    return {"success": False, "message": "Failed to enable TTS"}

@tts_router.post("/disable")
async def disable_tts():
    """禁用TTS"""
    success = await tts_service.disable_tts()
    if success:
        return {"success": True, "message": "TTS disabled"}
    return {"success": False, "message": "Failed to disable TTS"}

@tts_router.get("/status")
async def get_tts_status():
    """获取TTS状态"""
    status = tts_service.get_tts_status()
    return status

@tts_router.post("/generate")
async def generate_tts(request:requestFormatted):
    """生成TTS语音"""
    text = request.text
    character_name = request.character_name
    
    if not text:
        return {"error": "text is required"}
    
    try:
        # 使用TTS服务生成语音
        success = await tts_service.generate_speech(text, character_name=character_name)
        if success:
            return {"success": True, "message": "TTS generated successfully"}
        else:
            return {"success": False, "message": "TTS generation failed"}
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        return {"success": False, "message": str(e)}

@tts_router.post("/stream_generate")
async def stream_generate_tts(request:requestFormatted):
    """流式生成TTS语音"""
    text = request.text
    character_name = request.character_name
    
    if not text:
        return {"error": "text is required"}
    
    try:
        success = await tts_service.stream_generate_speech(text, character_name=character_name)
        if success:
            return {"success": True, "message": "TTS streamed successfully"}
        else:
            return {"success": False, "message": "TTS streaming failed"}
    except Exception as e:
        logger.error(f"TTS streaming error: {e}")
        return {"success": False, "message": str(e)}

