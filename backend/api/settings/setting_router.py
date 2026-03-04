from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 

from tools.utils import load_config, modify_config
from tools.config_manager import ConfigManager
from service.llm_factory import LLMFactory

settingRouter = APIRouter(
    prefix='/settings',
    tags=['settings'],
)

class modifyFomatter(BaseModel):
    key:str
    new_value:Any


class SwitchProviderRequest(BaseModel):
    provider: str


class ProviderInfo(BaseModel):
    name: str
    model: str
    enabled: bool
    is_current: bool

@settingRouter.get('/')
def load_all_config():
    """获取所有config配置信息，默认在'../data/config.yaml'

    Raises:
        HTTPException: 404      

    Returns:
        _type_: 配置文件字典
    """
    # logger.debug(Path.cwd())
    config = load_config('../data/config.yaml')
    if config is None:
        raise HTTPException(status_code=404,detail='配置文件加载失败')
    return config
        
@settingRouter.put('/modify_setting')
def modify_settings(modify_data:modifyFomatter):
    """修改配置

    Args:
        modify_data (modifyFomatter): 传入key_path和value
        - key_path: 路径字符串，例如 'providers.deepseek.api_key'
        - new_value: 新的值

    Raises:
        HTTPException: 500 没有配置成功 

    Returns:
        _type_: info
    """
    logger.info(f'修改配置项：{modify_data.key} | 新值：{modify_data.new_value}')
    success = modify_config(key_path=modify_data.key,new_value=modify_data.new_value,config_path='../data/config.yaml')
    if not success:
        raise HTTPException(status_code=500,detail='修改配置项失败')
    return {"message":"配置修改成功","key":modify_data.key,"new_value":modify_data.new_value}


@settingRouter.get("/providers")
async def list_providers():
    """获取所有可用的提供商列表"""
    factory = LLMFactory()
    config_manager = ConfigManager()

    available = factory.get_available_providers()
    current = factory.get_current_provider()

    providers_info = []
    for name in available:
        provider_config = config_manager.get_provider_config(name)
        if provider_config:
            providers_info.append({
                "name": name,
                "model": provider_config.model,
                "enabled": provider_config.enabled,
                "is_current": name == current
            })

    return {
        "providers": providers_info,
        "current": current
    }


@settingRouter.post("/providers/switch")
async def switch_provider(request: SwitchProviderRequest):
    """切换到指定的提供商"""
    try:
        factory = LLMFactory()
        new_instance = factory.switch_provider(request.provider)

        return {
            "success": True,
            "message": f"已切换到 {request.provider}",
            "provider": request.provider,
            "model": new_instance.model
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"切换提供商失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@settingRouter.get("/config")
async def get_config():
    """获取当前配置"""
    config_manager = ConfigManager()
    return {
        "config": config_manager.config,
        "current_provider": config_manager.get_current_provider()
    }


@settingRouter.post("config/reload")
async def reload_config():
    """手动重新加载配置"""
    config_manager = ConfigManager()
    success = config_manager.reload_config()

    if success:
        return {"success": True, "message": "配置已重新加载"}
    else:
        raise HTTPException(status_code=500, detail="重新加载配置失败")
