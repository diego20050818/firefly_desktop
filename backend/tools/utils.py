"""实用工具

Returns:
    _type_: _description_
"""

import os
from typing import Optional

from loguru import logger
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


if __name__ == '__main__':
    print(load_config())

