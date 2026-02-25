from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator, Union
from dataclasses import dataclass, field
from enum import Enum
import os
from ruamel.yaml import YAML
from loguru import logger

class ModelType(Enum):
    """模型类型枚举"""
    CHAT = "chat"
    EMBEDDING = "embedding"

@dataclass
class ToolCall:
    """工具调用数据结构 - 对齐 OpenAI/MCP 格式"""
    id: str
    type: str  # 通常为 'function'
    function: Dict[str, Any]  # {'name': '...', 'arguments': '...'}

@dataclass
class ChatMessage:
    """
    聊天消息数据结构 - 支持多模态
    content 可以是简单的字符串，也可以是符合 OpenAI Vision 标准的列表
    """
    role: str  # 'system', 'user', 'assistant'
    content: Union[str, List[Dict[str, Any]]] 
    name: Optional[str] = None
    tool_calls:Optional[List[ToolCall]] = None
    tool_call_id:Optional[str] = None
    
    @classmethod
    def create_text(cls, role: str, text: str):
        return cls(role=role, content=text)

    @classmethod
    def create_vision(cls, role: str, text: str, image_urls: List[str]):
        """创建包含图片的消息"""
        content = [{"type": "text", "text": text}]
        for url in image_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        return cls(role=role, content=content)

@dataclass
class ChatCompletionResponse:
    """聊天完成响应数据结构"""
    content: Optional[str]  # 可能是 None (如果只有 tool_calls)
    model: str
    usage: Dict[str, int]
    finish_reason: str
    tool_calls: Optional[List[ToolCall]] = None
    # DeepSeek R1/V3 特有的思维链内容
    reasoning_content: Optional[str] = None 
    created: Optional[int] = None

@dataclass
class EmbeddingResponse:
    embeddings: List[List[float]]
    model: str
    usage: Dict[str, int]

class LLMService(ABC):
    """LLM服务抽象基类"""
    provider_name:str = ""
    def __init__(self, config_path: str = "../data/config.yaml"):
        self.config_path = config_path
        self.base_config = self._load_config()
        
        # 基础配置检查
        if not self.base_config:
            logger.warning("Config loaded is empty")
        
        self.message:list[ChatMessage] = []
        self.message.append(ChatMessage.create_text("system",
                                                self.base_config.get('system_prompt','you are a helpful Assistant')))
    def _load_config(self) -> Dict[str, Any]:
        """安全加载配置文件"""
        try:
            yaml = YAML()
            yaml.preserve_quotes = True
            if not os.path.exists(self.config_path):
                logger.error(f"Config file not found: {self.config_path}")
                return {}
            
            with open(self.config_path, encoding='utf-8') as f:
                config = yaml.load(f) or {}
            logger.info(f"Config loaded from {self.config_path}")
            return config
        except Exception as e:
            logger.exception(f"Failed to load config: {e}")
            return {}
    def trans_ChatMessage_dict(self) -> List:
        """将self.message原本list[ChatMessage]格式转换为通用的[{'role':role,'content':content}]格式"""
        return [{"role": msg.role, "content": msg.content} for msg in self.message]

    @abstractmethod
    def _create_client(self, **kwargs) -> Any:
        pass

    def _init_tools(self,**kwargs) -> Any:
        pass
    
    @abstractmethod
    async def chat_completion(
        self,
        user_prompt:str,
        **kwargs
    ) -> ChatCompletionResponse | None:
        """非流式对话"""
        pass
    
    @abstractmethod
    async def stream_chat_completion(
        self,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionResponse, None]:
        """流式对话"""
        pass

    @abstractmethod
    async def chat(self,**kwargs):
        """对话"""
        pass
    @abstractmethod
    def save_to_history(self):
        """保存对话到历史文件"""
        pass

    @abstractmethod            
    def load_from_history(self):
        """从历史文件提取对话"""
        pass

    @abstractmethod
    async def generate_embedding(self, texts: List[str], model: Optional[str] = None) -> EmbeddingResponse:
        pass