# llm_registry.py
from typing import Dict, Type
from loguru import logger
from .llm_service import LLMService

_SERVICE_REGISTRY: Dict[str, Type[LLMService]] = {}

def register_provider(name: str):
    """装饰器：用于注册 LLM 服务提供者"""
    def decorator(cls: Type[LLMService]):
        _SERVICE_REGISTRY[name] = cls
        cls.provider_name = name
        return cls
    return decorator

def get_provider_class(name: str) -> Type[LLMService]:
    if name not in _SERVICE_REGISTRY:
        raise ValueError(f"Unknown provider: {name}")
    return _SERVICE_REGISTRY[name]

def list_providers() -> list[str]:
    return list(_SERVICE_REGISTRY.keys())

from .deepseek import DeepSeekService

logger.info(f"avaliable service:{list_providers()}")