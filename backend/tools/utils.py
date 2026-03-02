"""实用工具

Returns:
    _type_: _description_
"""

import os
from typing import Optional,Any

from loguru import logger
from pathlib import Path
from ruamel.yaml import YAML


def load_config(config_path='../../data/config.yaml') -> dict:
    """读取config.yaml配置文件

    Args:
        config_path (str, optional): config 文件目录. Defaults to '../../data/config.yaml'.

    Returns:
        dict | None: 如果没有找到配置文件就返回None
    """
    logger.info(f'read config {config_path} from path:{os.getcwd()}')
    yaml = YAML()
    try:
        with open(config_path,encoding='utf-8') as f:
            config = yaml.load(f)

        return config
    except Exception as e:
        logger.error(f"load config faile:{e}")
        return {}

def modify_config(key_path: str, new_value: Any, config_path: str = '../../data/config.yaml') -> bool:
    """
    修改嵌套 YAML 配置
    :param key_path: 路径字符串，例如 'providers.deepseek.api_key'
    :param new_value: 新的值
    """
    yaml = YAML()
    yaml.preserve_quotes = True  # 保留引号格式
    yaml.indent(mapping=2, sequence=4, offset=2) # 保持缩进美观
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.load(f)
        
        # 将路径 'a.b.c' 拆分为 ['a', 'b', 'c']
        keys = key_path.split('.')
        
        # 递归深入到倒数第二层
        target = config
        for key in keys[:-1]:
            # 如果中间层级不存在，自动创建（可选）
            if key not in target or target[key] is None:
                # target[key] = {}
                raise KeyError(f'{key}不存在')
            target = target[key]
        
        # 修改最后一层的值
        target[keys[-1]] = new_value
        
        # 写回文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f)
        
        return True
    except Exception as e:
        print(f'Failed to modify config: {e}')
        return False


if __name__ == '__main__':
    print(load_config())

