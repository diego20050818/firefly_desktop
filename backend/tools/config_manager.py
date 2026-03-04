"""
配置管理器 - 支持热更新的配置系统
监听配置文件变化，自动重新加载配置并更新服务实例
"""
import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field
from ruamel.yaml import YAML
from loguru import logger


@dataclass
class ProviderConfig:
    """单个提供商的配置"""
    name: str
    api_key: str
    base_url: str
    model: str
    enabled: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """配置管理器 - 单例模式"""
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.config_path = Path.cwd().parent / 'data' / 'config.yaml'
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        
        self._config_hash: Optional[str] = None
        self._config_data: Dict[str, Any] = {}
        self._callbacks: list[Callable] = []
        self._watch_task: Optional[asyncio.Task] = None
        self._is_watching = False
        
        # 初始加载配置
        self.reload_config()
        
        self._initialized = True
    
    def reload_config(self) -> bool:
        """重新加载配置文件
        
        Returns:
            bool: 是否成功加载
        """
        try:
            if not self.config_path.exists():
                logger.error(f"配置文件不存在：{self.config_path}")
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 计算哈希判断是否变化
            new_hash = hashlib.md5(content.encode()).hexdigest()
            
            if new_hash == self._config_hash:
                logger.debug("配置文件未变化，跳过重新加载")
                return True
            
            # 解析新配置
            new_config = self.yaml.load(content) or {}
            
            # 更新配置数据
            self._config_data = new_config
            self._config_hash = new_hash
            
            logger.info(f"配置已重新加载：{self.config_path}")
            
            # 触发回调
            self._notify_callbacks()
            
            return True
            
        except Exception as e:
            logger.error(f"重新加载配置失败：{e}")
            return False
    
    def register_callback(self, callback: Callable):
        """注册配置变更回调
        
        Args:
            callback: 回调函数，当配置变化时调用
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            logger.debug(f"已注册配置变更回调：{callback.__name__}")
    
    def unregister_callback(self, callback: Callable):
        """注销配置变更回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self):
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback())
                else:
                    callback()
            except Exception as e:
                logger.error(f"执行配置变更回调失败 {callback.__name__}: {e}")
    
    def start_watching(self, interval: float = 5.0):
        """开始监听配置文件变化
        
        Args:
            interval: 检查间隔（秒），默认 5 秒
        """
        if self._is_watching:
            logger.warning("配置监听已在运行")
            return
        
        self._is_watching = True
        self._watch_task = asyncio.create_task(
            self._watch_config_loop(interval)
        )
        logger.info(f"开始监听配置文件变化，间隔：{interval}秒")
    
    def stop_watching(self):
        """停止监听配置文件"""
        self._is_watching = False
        if self._watch_task:
            self._watch_task.cancel()
            logger.info("已停止监听配置文件")
    
    async def _watch_config_loop(self, interval: float):
        """监听配置文件变化的循环"""
        try:
            while self._is_watching:
                await asyncio.sleep(interval)
                
                # 检查文件是否变化
                if self.config_path.exists():
                    mtime = self.config_path.stat().st_mtime
                    
                    # 如果文件修改时间比上次检查晚，重新加载
                    if not hasattr(self, '_last_mtime') or mtime > self._last_mtime:
                        self._last_mtime = mtime
                        self.reload_config()
                        
        except asyncio.CancelledError:
            logger.debug("配置监听任务已取消")
        except Exception as e:
            logger.error(f"配置监听出错：{e}")
    
    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """获取指定提供商的配置
        
        Args:
            provider_name: 提供商名称（如 'deepseek', 'openai'）
            
        Returns:
            ProviderConfig 对象，如果配置不存在返回 None
        """
        providers = self._config_data.get('providers', {})
        provider_data = providers.get(provider_name)
        
        if not provider_data:
            return None
        
        return ProviderConfig(
            name=provider_name,
            api_key=provider_data.get('api_key', ''),
            base_url=provider_data.get('base_url', ''),
            model=provider_data.get('model', ''),
            enabled=provider_data.get('enabled', True),
            extra={k: v for k, v in provider_data.items() 
                   if k not in ['api_key', 'base_url', 'model', 'enabled']}
        )
    
    def get_all_providers(self) -> list[str]:
        """获取所有已配置的提供商名称"""
        providers = self._config_data.get('providers', {})
        return [
            name for name, config in providers.items()
            if config.get('enabled', True)
        ]
    
    def get_current_provider(self) -> str:
        """获取当前使用的提供商"""
        return self._config_data.get('current_provider', 'deepseek')
    
    def set_current_provider(self, provider_name: str) -> bool:
        """设置当前使用的提供商
        
        Args:
            provider_name: 要切换的提供商名称
            
        Returns:
            bool: 是否设置成功
        """
        available = self.get_all_providers()
        if provider_name not in available:
            logger.error(f"提供商 {provider_name} 不存在或未启用")
            return False
        
        self._config_data['current_provider'] = provider_name
        logger.info(f"已切换到提供商：{provider_name}")
        return True
    
    @property
    def config(self) -> Dict[str, Any]:
        """获取完整配置字典"""
        return self._config_data