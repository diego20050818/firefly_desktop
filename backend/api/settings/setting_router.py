from typing import Any
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from loguru import logger
from pathlib import Path 

from tools.utils import load_config, modify_config

settingRouter = APIRouter(
    prefix='/settings',
    tags=['settings'],
)

class modifyFomatter(BaseModel):
    key:str
    new_value:Any

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
