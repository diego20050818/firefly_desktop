"""
LLM 工厂 - 动态创建和管理 LLM 服务实例
支持运行时切换不同的提供商
"""
from typing import Dict, Optional, Type
from loguru import logger

from .llm_service import LLMService
from .llm_register import get_provider_class, _SERVICE_REGISTRY
from tools.config_manager import ConfigManager, ProviderConfig


class LLMFactory:
    """LLM 工厂类 - 管理所有 LLM 服务实例"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._instances: Dict[str, LLMService] = {}
            cls._instance._current_provider: Optional[str] = None
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.config_manager = ConfigManager()
        self._instances: Dict[str, LLMService] = {}
        self._current_provider: Optional[str] = None

        # 注册配置变更回调
        self.config_manager.register_callback(self._on_config_change)

        self._initialized = True

    def _on_config_change(self):
        """配置变更时的处理 - 清空缓存以便下次获取时使用新配置"""
        logger.info("检测到配置变更，清空 LLM 实例缓存...")

        # 清空所有缓存的实例，这样下次调用 get_instance 时会重新创建
        old_providers = list(self._instances.keys())
        self.clear_cache()

        logger.info(f"已清空 {len(old_providers)} 个 LLM 实例缓存，下次请求时将使用新配置")

    def get_instance(self, provider_name: Optional[str] = None) -> LLMService:
        """获取或创建 LLM 服务实例

        Args:
            provider_name: 提供商名称，如果不提供则使用当前配置的提供商

        Returns:
            LLMService 实例
        """
        # 如果没有指定提供商，使用配置的当前提供商
        if provider_name is None:
            provider_name = self.config_manager.get_current_provider()

        # 如果已经有实例，直接返回
        if provider_name in self._instances:
            logger.debug(f"使用缓存的 {provider_name} 实例")
            return self._instances[provider_name]

        # 创建新实例（会重新读取配置文件）
        try:
            service_cls = get_provider_class(provider_name)
            instance = service_cls()

            self._instances[provider_name] = instance
            self._current_provider = provider_name

            logger.info(f"已创建 {provider_name} LLM 服务实例 | 模型：{instance.model}")
            return instance

        except Exception as e:
            logger.error(f"创建 {provider_name} 实例失败：{e}")
            raise

    def switch_provider(self, provider_name: str) -> LLMService:
        """切换到指定的 LLM 提供商

        Args:
            provider_name: 要切换的提供商名称

        Returns:
            新的 LLMService 实例
        """
        # 验证提供商是否可用
        available = self.config_manager.get_all_providers()
        if provider_name not in available:
            raise ValueError(
                f"提供商 {provider_name} 不存在或未启用。"
                f"可用的提供商：{available}"
            )

        # 如果已经在用这个提供商且配置未变化，直接返回
        if self._current_provider == provider_name and provider_name in self._instances:
            # 检查配置是否变化
            current_model = self._instances[provider_name].model
            config_model = self.config_manager.get_provider_config(
                provider_name).model

            if current_model == config_model:
                logger.info(f"已经在使用 {provider_name} ({current_model})")
                return self._instances[provider_name]
            else:
                logger.info(f"配置发生变化：{current_model} -> {config_model}，重新创建实例")
                # 配置变化，需要重新创建
                del self._instances[provider_name]

        # 获取或创建新实例
        new_instance = self.get_instance(provider_name)

        # 更新当前提供商
        self._current_provider = provider_name
        self.config_manager.set_current_provider(provider_name)

        logger.success(f"已切换到 {provider_name} 提供商 | 模型：{new_instance.model}")
        return new_instance

    def get_current_provider(self) -> str:
        """获取当前使用的提供商"""
        return self._current_provider or self.config_manager.get_current_provider()

    def get_available_providers(self) -> list[str]:
        """获取所有可用的提供商"""
        return self.config_manager.get_all_providers()

    def preload_all_providers(self):
        """预加载所有可用的提供商实例"""
        providers = self.get_available_providers()
        logger.info(f"预加载 {len(providers)} 个提供商：{providers}")

        for provider in providers:
            try:
                self.get_instance(provider)
                logger.success(f"{provider} 预加载完成")
            except Exception as e:
                logger.error(f"{provider} 预加载失败：{e}")

    def clear_cache(self):
        """清空所有缓存的实例"""
        self._instances.clear()
        self._current_provider = None
        logger.info("已清空所有 LLM 实例缓存")
