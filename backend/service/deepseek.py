from ruamel.yaml import YAML
import os
from openai import OpenAI
from loguru import logger
import asyncio
import json
from pathlib import Path
from datetime import datetime

from typing import Any, AsyncGenerator, Dict, List, Optional
import openai
from openai import AsyncOpenAI

from .llm_service import LLMService
from .llm_service import ModelType, ChatMessage, ToolCall, ChatCompletionResponse, EmbeddingResponse

from .llm_register import register_provider


@register_provider("deepseek")
class DeepSeekService(LLMService):
    def __init__(self, config_path: str = "../data/config.yaml"):
        super().__init__(config_path)
        self.config_path = config_path

        # 基础配置检查
        if not self.base_config:
            logger.error("Config loaded is empty")
            raise KeyError(f"base config is empty:config_path:{self.config_path} current path:{os.getcwd()}")
            
        self.deepseek_config = self.base_config['providers']['deepseek']

        if not self.base_config or not self.deepseek_config:
            logger.error("config loaded failed or it is empty")
            raise ValueError
        
        self.client: AsyncOpenAI = self._create_client()
        
        # 历史记录配置
        self.history_dir = Path(self.base_config.get('history_dir', './history'))
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _create_client(self, **kwargs) -> Any:
        """创建openai客户端

        Raises:
            ValueError: 输入的是config.yaml的deepseek api和base url，如果报错则检查空格、导入相对情况

        Returns:
            Any: 返回客户端本身
        """
        self.api_key = self.deepseek_config.get("api_key")
        self.base_url = self.deepseek_config.get("base_url", "https://api.deepseek.com")
        self.model = self.deepseek_config.get("model", "deepseek-chat")

        if self.model is None:
            logger.warning(f"model is None, check your config file: {self.config_path}, use default: {self.model}")

        if self.api_key is None:
            logger.error("cannot find your api key")
            raise ValueError
        
        if self.deepseek_config['base_url'] is None:
            logger.warning(f"base url use default value: {self.base_url}")

        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    async def chat_completion(self, user_prompt: str, **kwargs) -> ChatCompletionResponse | None:
        """普通输出的对话方法

        Args:
            user_prompt: 用户输入的提示词
            **kwargs: 额外参数，如 temperature, max_tokens, tools 等

        Returns:
            ChatCompletionResponse | None: 输出的对话响应
        """
        # 检查是否启用思考模式
        extra_body = None
        if self.base_config.get("thinking") or kwargs.get('thinking'):
            extra_body = {"thinking": {"type": "enabled"}}

        # 添加用户消息
        self.message.append(ChatMessage.create_text(
            "user",
            user_prompt
        ))


        # 提取工具调用参数
        tools = kwargs.pop('tools', None)
        tool_choice = kwargs.pop('tool_choice', None)
        
        # 构建请求参数
        request_params = {
            "model": self.model,
            "messages": self.trans_ChatMessage_dict(),
            **kwargs
        }
        
        if extra_body:
            request_params["extra_body"] = extra_body
        

        request_params["tools"] = tools
        if tool_choice:
            request_params["tool_choice"] = tool_choice

        # 调用API
        response = await self.client.chat.completions.create(**request_params)

        choice = response.choices[0]
        assistant_response = choice.message

        # 提取推理内容（如果有）
        reasoning = getattr(assistant_response, 'reasoning_content', None)
        
        # 提取工具调用（如果有）
        tool_calls_data = None
        if assistant_response.tool_calls:
            tool_calls_data = [
                ToolCall(
                    id=tc.id,
                    type=tc.type,
                    function={
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                )
                for tc in assistant_response.tool_calls
            ]

        # 添加助手消息到历史
        self.message.append(
            ChatMessage(
                role='assistant',
                content=assistant_response.content or "",
                tool_calls=tool_calls_data
            )
        )

        return ChatCompletionResponse(
            content=assistant_response.content,
            model=response.model,
            usage=response.usage.model_dump() if response.usage else {},
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls_data,
            reasoning_content=reasoning,
            created=response.created
        )
    
    async def stream_chat_completion(
        self, 
        user_prompt: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionResponse, None]:
        """流式对话方法

        Args:
            user_prompt: 用户输入的提示词
            **kwargs: 额外参数

        Yields:
            ChatCompletionResponse: 流式返回的对话片段
        """
        # 检查是否启用思考模式
        extra_body = None
        if self.base_config.get("thinking") or kwargs.get('thinking'):
            extra_body = {"thinking": {"type": "enabled"}}

        # 添加用户消息
        self.message.append(ChatMessage.create_text(
            "user",
            user_prompt
        ))

        # 提取工具调用参数
        tools = kwargs.pop('tools', None)
        tool_choice = kwargs.pop('tool_choice', None)
        
        # 构建请求参数
        request_params = {
            "model": self.model,
            "messages": self.trans_ChatMessage_dict(),
            "stream": True,
            "stream_options": {"include_usage": True},
            **kwargs
        }
        
        if extra_body:
            request_params["extra_body"] = extra_body
        
        if tools:
            request_params["tools"] = tools
            if tool_choice:
                request_params["tool_choice"] = tool_choice

        # 调用流式API
        stream = await self.client.chat.completions.create(**request_params)

        # 用于累积完整响应
        full_content = ""
        reasoning_content = None
        collected_tool_calls = []
        finish_reason = None
        final_usage = {}  # 存储最终的 usage 信息
        
        async for chunk in stream:
            if not chunk.choices:
                continue
                
            choice = chunk.choices[0]
            delta = choice.delta
            
            # 处理内容
            if delta.content:
                full_content += delta.content
                
            # 处理推理内容
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                if reasoning_content is None:
                    reasoning_content = ""
                reasoning_content += delta.reasoning_content
            
            # 处理工具调用
            if delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    # 确保有足够的位置
                    while len(collected_tool_calls) <= tool_call_chunk.index:
                        collected_tool_calls.append({
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        })
                    
                    # 累积工具调用信息
                    if tool_call_chunk.id:
                        collected_tool_calls[tool_call_chunk.index]["id"] = tool_call_chunk.id
                    if tool_call_chunk.function:
                        if tool_call_chunk.function.name:
                            collected_tool_calls[tool_call_chunk.index]["function"]["name"] += tool_call_chunk.function.name
                        if tool_call_chunk.function.arguments:
                            collected_tool_calls[tool_call_chunk.index]["function"]["arguments"] += tool_call_chunk.function.arguments
            
            # 检查是否是结束块并包含 usage 信息
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            
            # 检查 chunk 是否包含 usage 信息（通常在最后一个块中）
            if hasattr(chunk, 'usage') and chunk.usage:
                final_usage = chunk.usage.model_dump() if hasattr(chunk.usage, 'model_dump') else {}
            
            # 返回当前片段
            yield ChatCompletionResponse(
                content=delta.content or "",
                model=chunk.model,
                usage={},  # 流式模式下单个片段通常不包含usage
                finish_reason=choice.finish_reason,
                tool_calls=None,  # 流式模式下工具调用在最后才完整
                reasoning_content=delta.reasoning_content if hasattr(delta, 'reasoning_content') else None,
                created=chunk.created
            )
        
        # 转换工具调用格式
        tool_calls_data = None
        if collected_tool_calls:
            tool_calls_data = [
                ToolCall(
                    id=tc["id"],
                    type=tc["type"],
                    function=tc["function"]
                )
                for tc in collected_tool_calls
            ]
        
        # 添加完整的助手消息到历史
        self.message.append(
            ChatMessage(
                role='assistant',
                content=full_content,
                tool_calls=tool_calls_data
            )
        )
        
        logger.debug(f"Stream completed. Full content length: {len(full_content)}")
        
        # 返回带有完整 usage 信息的最终响应（如果需要）
        # 注意：这个最终响应不通过 yield 返回，因为流已经结束
        # 但我们可以在最后的完整响应中使用 final_usage

    async def chat(self, **kwargs):
        """交互式聊天循环"""
        logger.info("开始交互式聊天，输入 'q', 'quit' 或 'exit' 退出")
        logger.info(r"输入 '\save' 保存对话历史，输入 '\load' 加载对话历史")
        
        while True:
            user_input = input("\n👤 User: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['q', 'quit', 'exit']:
                logger.info("退出聊天")
                break
            
            if user_input.lower() == r'\save':
                self.save_to_history()
                logger.info("对话历史已保存")
                continue
            
            if user_input.lower() == r'\load':
                session_id = input("请输入要加载的会话ID（留空加载最新）: ").strip()
                self.load_from_history(session_id if session_id else None)
                logger.info("对话历史已加载")
                continue
            
            if user_input.lower() == r'\clear':
                self.message = []
                logger.info("对话历史已清空")
                continue
            
            # 检查是否使用流式模式
            use_stream = kwargs.get('stream', False)
            
            try:
                if use_stream:
                    print("\n🤖 Assistant: ", end='', flush=True)
                    async for chunk in self.stream_chat_completion(user_prompt=user_input, **kwargs):
                        if chunk.content:
                            print(chunk.content, end='', flush=True)
                        if chunk.reasoning_content:
                            # 在流式模式下实时显示思考过程
                            print(f"\n💭 [思考] {chunk.reasoning_content}", end='', flush=True)
                    print()  # 换行
                else:
                    response: ChatCompletionResponse = await self.chat_completion(
                        user_prompt=user_input,
                        **kwargs
                    )  # type: ignore
                    
                    if response.reasoning_content:
                        print("\n💭 ///////// 思考过程 /////////")
                        print(response.reasoning_content)
                    
                    if response.tool_calls:
                        print("\n🛠️  ///////// 工具调用 /////////")
                        for tool_call in response.tool_calls:
                            print(f"工具: {tool_call.function['name']}")
                            print(f"参数: {tool_call.function['arguments']}")
                    
                    print("\n🤖 ///////// 回答 /////////")
                    print(response.content)
                    
                    if response.usage:
                        print(f"\n📊 Token使用: {response.usage}")
                        
            except Exception as e:
                logger.error(f"对话出错: {e}")
                print(f"❌ 错误: {e}")
    
    def save_to_history(self, session_id: Optional[str] = None) -> str:
        """保存对话历史到文件

        Args:
            session_id: 会话ID，如果不提供则自动生成

        Returns:
            str: 保存的会话ID
        """
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        history_file = self.history_dir / f"session_{session_id}.json"
        
        # 转换消息为可序列化格式
        messages_data = []
        for msg in self.message:
            msg_dict = {
                "role": msg.role,
                "content": msg.content
            }
            if msg.name:
                msg_dict["name"] = msg.name
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": tc.function
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            messages_data.append(msg_dict)
        
        # 保存到文件
        history_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "model": self.model,
            "messages": messages_data
        }
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"对话历史已保存到: {history_file}")
        return session_id
    
    def load_from_history(self, session_id: Optional[str] = None) -> bool:
        """从文件加载对话历史

        Args:
            session_id: 会话ID，如果不提供则加载最新的会话

        Returns:
            bool: 是否加载成功
        """
        try:
            if session_id:
                history_file = self.history_dir / f"session_{session_id}.json"
            else:
                # 查找最新的会话文件
                session_files = list(self.history_dir.glob("session_*.json"))
                if not session_files:
                    logger.warning("没有找到历史会话文件")
                    return False
                history_file = max(session_files, key=lambda p: p.stat().st_mtime)
            
            if not history_file.exists():
                logger.error(f"会话文件不存在: {history_file}")
                return False
            
            # 加载历史数据
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # 恢复消息
            self.message = []
            for msg_data in history_data['messages']:
                tool_calls = None
                if 'tool_calls' in msg_data:
                    tool_calls = [
                        ToolCall(
                            id=tc['id'],
                            type=tc['type'],
                            function=tc['function']
                        )
                        for tc in msg_data['tool_calls']
                    ]
                
                self.message.append(
                    ChatMessage(
                        role=msg_data['role'],
                        content=msg_data['content'],
                        name=msg_data.get('name'),
                        tool_calls=tool_calls,
                        tool_call_id=msg_data.get('tool_call_id')
                    )
                )
            
            logger.info(f"已加载会话: {history_data['session_id']} (共 {len(self.message)} 条消息)")
            return True
            
        except Exception as e:
            logger.error(f"加载对话历史失败: {e}")
            return False
    
    async def generate_embedding(
        self, 
        texts: List[str], 
        model: Optional[str] = None
    ) -> EmbeddingResponse:
        """生成文本嵌入向量

        Args:
            texts: 要生成嵌入的文本列表
            model: 嵌入模型名称，默认使用配置中的模型

        Returns:
            EmbeddingResponse: 嵌入响应，包含向量和使用信息
        """
        if not texts:
            logger.warning("文本列表为空")
            return EmbeddingResponse(
                embeddings=[],
                model="",
                usage={}
            )
        
        # 使用配置中的嵌入模型或默认模型
        embedding_model = model or self.deepseek_config.get('embedding_model', 'text-embedding-ada-002')
        
        try:
            # 调用OpenAI兼容的嵌入API
            response = await self.client.embeddings.create(
                model=embedding_model,
                input=texts
            )
            
            # 提取嵌入向量
            embeddings = [item.embedding for item in response.data]
            
            # 提取使用信息
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            
            logger.info(f"成功生成 {len(embeddings)} 个嵌入向量，维度: {len(embeddings[0]) if embeddings else 0}")
            
            return EmbeddingResponse(
                embeddings=embeddings,
                model=response.model,
                usage=usage
            )
            
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {e}")
            # 返回空响应
            return EmbeddingResponse(
                embeddings=[],
                model=embedding_model,
                usage={}
            )


if __name__ == '__main__':
    # 测试代码
    async def main():
        # 创建DeepSeek服务实例
        ds_client = DeepSeekService()
        
        # 测试普通对话
        print("=== 测试普通对话 ===")
        response = await ds_client.chat_completion("你好，请介绍一下你自己")
        print(f"回复: {response.content}")
        
        # 测试流式对话
        print("\n=== 测试流式对话 ===")
        print("回复: ", end='', flush=True)
        async for chunk in ds_client.stream_chat_completion("用一句话介绍Python"):
            if chunk.content:
                print(chunk.content, end='', flush=True)
        print()
        
        # 测试保存历史
        print("\n=== 测试保存历史 ===")
        session_id = ds_client.save_to_history()
        print(f"会话ID: {session_id}")
        
        # 测试加载历史
        print("\n=== 测试加载历史 ===")
        ds_client.message = []  # 清空当前消息
        ds_client.load_from_history(session_id)
        print(f"加载了 {len(ds_client.message)} 条消息")
        
        # 测试嵌入生成
        print("\n=== 测试嵌入生成 ===")
        embedding_response = await ds_client.generate_embedding([
            "人工智能是什么",
            "机器学习的应用"
        ])
        print(f"生成了 {len(embedding_response.embeddings)} 个嵌入向量")
        if embedding_response.embeddings:
            print(f"向量维度: {len(embedding_response.embeddings[0])}")
        
        # 启动交互式聊天
        print("\n=== 启动交互式聊天 ===")
        await ds_client.chat(stream=True)
    
    asyncio.run(main())
    logger.debug("测试完成")