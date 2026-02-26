"""对话代理模块 - 编排 LLM 与 MCP 工具调用的核心引擎。

该模块实现了 ChatAgent 类，负责管理对话上下文，并在 LLM 返回
tool_calls 时自动执行对应的 MCP 工具，再将执行结果反馈给 LLM，
形成完整的"思考-调用-反馈"闭环。

遵循 DeepSeek ToolCalls 官方文档的消息格式：
  1. 用户消息 -> LLM
  2. LLM 返回 tool_calls (finish_reason='tool_calls')
  3. 将 assistant 消息（含 tool_calls）追加到 messages
  4. 执行工具，将结果以 role='tool' + tool_call_id 追加到 messages
  5. 再次调用 LLM，获取最终回复

参考: https://api-docs.deepseek.com/zh-cn/guides/tool_calls
"""

import json
from typing import Any, AsyncGenerator, Optional

from loguru import logger

from service.llm_register import get_provider_class
from service.llm_service import (
    ChatCompletionResponse,
    ChatMessage,
    LLMService,
    ToolCall,
)
from tools.registry_tools import tool_registry


def convert_mcp_tools_to_openai_schema() -> list[dict[str, Any]]:
    """将 MCP 注册的工具转换为 DeepSeek/OpenAI 兼容的 tools JSON Schema。

    DeepSeek 要求的 tools 格式:
    [
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "工具描述",
                "parameters": { ... JSON Schema ... }
            }
        }
    ]

    Returns:
        符合 OpenAI/DeepSeek API 规范的工具定义列表。
    """
    tools_schema = []
    # 从缓存获取所有已加载的工具（包含本地 FastMCP 和外部 Stdio/HTTP MCP）
    all_tools = tool_registry.get_cached_tools()

    for tool_info in all_tools:
        tool_def = {
            "type": "function",
            "function": {
                "name": tool_info.name,
                "description": tool_info.description or "",
                "parameters": tool_info.parameters or {
                    "type": "object",
                    "properties": {},
                },
            },
        }
        tools_schema.append(tool_def)

    logger.info(f"已转换 {len(tools_schema)} 个 MCP 工具为 OpenAI Schema")
    return tools_schema


async def execute_tool_call(tool_call: ToolCall) -> str:
    """执行单个工具调用，返回工具执行结果字符串。

    该函数从 tool_registry 中查找对应的 MCP 工具并执行。
    支持本地 FastMCP 注册的工具。

    Args:
        tool_call: 包含工具名称和参数的 ToolCall 对象。

    Returns:
        工具执行结果的字符串表示。如果执行失败，返回错误信息。
    """
    func_name = tool_call.function.get("name", "")
    arguments_str = tool_call.function.get("arguments", "{}")

    logger.info(f"正在执行工具: {func_name}, 参数: {arguments_str}")

    try:
        # 解析参数 JSON
        arguments = json.loads(arguments_str)
    except json.JSONDecodeError as e:
        error_msg = f"工具参数解析失败: {e}"
        logger.error(error_msg)
        return error_msg

    try:
        # 1. 优先尝试从本地 FastMCP 注册表中查找
        from tools.launch_app import mcp as local_mcp

        if func_name in local_mcp._tool_manager._tools:
            tool_obj = local_mcp._tool_manager._tools[func_name]
            # 调用 FastMCP 工具的 run 方法
            # 返回值是 ToolResult 对象，需要提取其中的文本内容
            tool_result = await tool_obj.run(arguments)

            # 从 ToolResult 中提取文本结果
            if hasattr(tool_result, "content") and tool_result.content:
                result_str = "\n".join(
                    item.text
                    for item in tool_result.content
                    if hasattr(item, "text")
                )
            else:
                result_str = str(tool_result)

            logger.info(f"本地工具 {func_name} 执行成功: {result_str[:200]}")
            return result_str
            
        # 2. 如果本地不存在，则尝试从外部 Stdio MCP 服务器调用
        from tools.stdio_mcp import stdio_mcp_manager
        
        # stdio_mcp_manager 内部会查路由表并分发
        # 若均未找到，则会抛出 ValueError
        result_str = await stdio_mcp_manager.call_tool(func_name, arguments)
        logger.info(f"外部 MCP 工具 {func_name} 执行成功: {result_str[:200]}")
        return result_str

    except ValueError as e:
        # ValueError 表示在任何注册表都没找到工具
        error_msg = str(e)
        logger.warning(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"工具 {func_name} 执行异常: {str(e)}"
        logger.error(error_msg)
        return error_msg


class ChatAgent:
    """对话代理 - 协调 LLM 对话与 MCP 工具调用。

    该类封装了完整的对话流程：
    1. 接受用户输入
    2. 调用 LLM（附带可用工具列表）
    3. 如果 LLM 返回 tool_calls，自动执行工具并将结果反馈
    4. 循环直到 LLM 给出最终文本回复

    Attributes:
        llm_service: LLM 服务实例（如 DeepSeekService）。
        tools_schema: 转换后的 OpenAI 格式工具定义列表。
        max_tool_rounds: 单次对话中最大工具调用轮数，防止死循环。
    """

    def __init__(
        self,
        provider: str = "deepseek",
        max_tool_rounds: int = 5,
    ) -> None:
        """初始化 ChatAgent。

        Args:
            provider: LLM 服务提供商名称，默认 "deepseek"。
            max_tool_rounds: 最大工具调用轮数，默认 5。
        """
        # 获取 LLM 服务类并实例化
        provider_cls = get_provider_class(provider)
        self.llm_service: LLMService = provider_cls()

        # 加载 MCP 工具并转换为 OpenAI Schema
        self.tools_schema = convert_mcp_tools_to_openai_schema()
        self.max_tool_rounds = max_tool_rounds

        logger.info(
            f"ChatAgent 初始化完成 | 提供商: {provider} | "
            f"可用工具: {len(self.tools_schema)}"
        )

    async def chat(self, user_prompt: str) -> dict[str, Any]:
        """处理用户输入，自动编排工具调用，返回最终结果。

        完整的对话流程:
        1. 将 tools_schema 传入 LLM 请求
        2. 如果 LLM 返回 tool_calls → 执行工具 → 反馈结果 → 重新请求
        3. 直到 LLM 返回纯文本回复

        Args:
            user_prompt: 用户输入的文本。

        Returns:
            包含以下字段的字典:
            - content: LLM 最终回复文本
            - tool_calls_history: 本次对话中的所有工具调用记录
            - reasoning_content: 推理内容（如果有）
            - usage: Token 使用统计
        """
        tool_calls_history = []

        # 第一轮: 带工具列表调用 LLM
        response = await self.llm_service.chat_completion(
            user_prompt=user_prompt,
            tools=self.tools_schema if self.tools_schema else None,
        )

        if response is None:
            logger.error("LLM 返回空响应")
            return {
                "content": "抱歉，我暂时无法回答这个问题。",
                "tool_calls_history": [],
                "reasoning_content": None,
                "usage": {},
            }

        # 工具调用循环
        round_count = 0
        while (
            response.tool_calls
            and response.finish_reason == "tool_calls"
            and round_count < self.max_tool_rounds
        ):
            round_count += 1
            logger.info(f"工具调用轮次 {round_count}/{self.max_tool_rounds}")

            # 逐个执行工具调用
            for tc in response.tool_calls:
                tool_result = await execute_tool_call(tc)

                # 记录工具调用历史
                tool_calls_history.append({
                    "tool_name": tc.function.get("name", ""),
                    "arguments": tc.function.get("arguments", "{}"),
                    "result": tool_result,
                    "round": round_count,
                })

                # 将工具结果以 role='tool' 的消息追加到对话历史
                # 这是 DeepSeek ToolCalls 文档要求的格式
                self.llm_service.message.append(
                    ChatMessage(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tc.id,
                    )
                )

            # 以更新后的 messages 再次调用 LLM（不再传 tools，等待最终回复）
            # 注意: DeepSeek 文档中，第二轮调用仍然可以传 tools，
            # 这样 LLM 可以选择继续调用工具或给出最终回复
            response = await self._call_llm_without_new_user_msg(
                tools=self.tools_schema if self.tools_schema else None,
            )

            if response is None:
                logger.error("工具反馈后 LLM 返回空响应")
                break

        # 返回最终结果
        return {
            "content": response.content if response else "",
            "tool_calls_history": tool_calls_history,
            "reasoning_content": (
                response.reasoning_content if response else None
            ),
            "usage": response.usage if response else {},
        }

    async def _call_llm_without_new_user_msg(
        self,
        tools: Optional[list[dict]] = None,
    ) -> Optional[ChatCompletionResponse]:
        """在不添加新用户消息的情况下调用 LLM。

        用于工具执行结果反馈后的后续调用。直接使用已有的
        message 历史（包含 tool 角色的消息）进行请求。

        Args:
            tools: 可选的工具定义列表，允许 LLM 继续调用工具。

        Returns:
            LLM 的响应，如果失败返回 None。
        """
        try:
            messages = self._build_messages_for_api()

            request_params = {
                "model": self.llm_service.model,
                "messages": messages,
            }

            # 注意: 工具反馈阶段不启用 thinking 模式，
            # 因为部分 DeepSeek 版本在 tool 消息 + thinking 同时存在时
            # 可能出现兼容性问题
            if tools:
                request_params["tools"] = tools

            logger.debug(
                f"后续 LLM 调用 | 消息数: {len(messages)} | "
                f"工具数: {len(tools) if tools else 0}"
            )

            # 直接调用底层 client
            api_response = await self.llm_service.client.chat.completions.create(
                **request_params
            )

            choice = api_response.choices[0]
            assistant_msg = choice.message

            # 提取推理内容
            reasoning = getattr(assistant_msg, "reasoning_content", None)

            # 提取工具调用
            tool_calls_data = None
            if assistant_msg.tool_calls:
                tool_calls_data = [
                    ToolCall(
                        id=tc.id,
                        type=tc.type,
                        function={
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    )
                    for tc in assistant_msg.tool_calls
                ]

            # 追加助手消息到历史
            self.llm_service.message.append(
                ChatMessage(
                    role="assistant",
                    content=assistant_msg.content or "",
                    tool_calls=tool_calls_data,
                )
            )

            return ChatCompletionResponse(
                content=assistant_msg.content,
                model=api_response.model,
                usage=(
                    api_response.usage.model_dump()
                    if api_response.usage else {}
                ),
                finish_reason=choice.finish_reason,
                tool_calls=tool_calls_data,
                reasoning_content=reasoning,
                created=api_response.created,
            )

        except Exception as e:
            import traceback
            logger.error(
                f"LLM 后续调用失败: {e}\n{traceback.format_exc()}"
            )
            return None

    def _build_messages_for_api(self) -> list[dict[str, Any]]:
        """将内部消息历史转换为 API 请求格式。

        处理不同角色的消息格式差异：
        - 普通消息: {"role": ..., "content": ...}
        - 助手消息带 tool_calls: 需包含 tool_calls 字段
        - 工具结果消息: 需包含 tool_call_id 字段

        Returns:
            符合 OpenAI/DeepSeek API 的消息列表。
        """
        messages = []
        for msg in self.llm_service.message:
            msg_dict: dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }

            # 助手消息附带工具调用
            if msg.role == "assistant" and msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": tc.function,
                    }
                    for tc in msg.tool_calls
                ]

            # 工具结果消息
            if msg.role == "tool" and msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id

            messages.append(msg_dict)

        return messages

    def reset(self) -> None:
        """重置对话历史，保留 system prompt。"""
        if self.llm_service.message:
            system_msg = self.llm_service.message[0]
            self.llm_service.message = [system_msg]
            logger.info("对话历史已重置（保留 system prompt）")
        else:
            self.llm_service.message = []
            logger.info("对话历史已清空")

    # ================================================================
    # 流式对话 API
    # ================================================================

    async def stream_chat(
        self, user_prompt: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式处理用户输入，逐 token 推送结果。

        与 chat() 类似，但以异步生成器方式逐步 yield 事件：
        - {"type": "reasoning", "content": "..."}  思考内容片段
        - {"type": "token", "content": "..."}      文本 token 片段
        - {"type": "tool_start", "tool_name": "...", "arguments": "..."}
        - {"type": "tool_end", "tool_name": "...", "result": "..."}
        - {"type": "done", "full_content": "...", "tool_calls_history": [...]}

        支持多轮对话：消息会累积在 llm_service.message 中，
        多次调用 stream_chat() 即可实现多轮上下文。

        Args:
            user_prompt: 用户输入的文本。

        Yields:
            事件字典，包含 type 和对应的内容。
        """
        tool_calls_history: list[dict[str, Any]] = []

        # 添加用户消息到历史
        self.llm_service.message.append(
            ChatMessage.create_text("user", user_prompt)
        )

        # 第一轮：流式调用 LLM（附带工具列表）
        stream_result = await self._stream_llm_call(
            tools=self.tools_schema if self.tools_schema else None,
            yield_tokens=True,
        )

        # 逐 token yield
        async for event in stream_result["stream"]:
            yield event

        # 等待生产者完成，然后从 _result 容器中读取结果
        # （stream 消费完毕后 _result 才会被填充）
        await stream_result["_task"]
        result = stream_result["_result"]
        collected_tool_calls = result["tool_calls"]
        full_content = result["full_content"]
        reasoning_content = result["reasoning_content"]
        finish_reason = result["finish_reason"]

        # 工具调用循环
        round_count = 0
        while (
            collected_tool_calls
            and finish_reason == "tool_calls"
            and round_count < self.max_tool_rounds
        ):
            round_count += 1
            logger.info(
                f"流式工具调用轮次 {round_count}/{self.max_tool_rounds}"
            )

            # 逐个执行工具调用
            for tc in collected_tool_calls:
                tool_name = tc.function.get("name", "")
                tool_args = tc.function.get("arguments", "{}")

                # 通知前端：工具开始执行
                yield {
                    "type": "tool_start",
                    "tool_name": tool_name,
                    "arguments": tool_args,
                }

                # 执行工具
                tool_result = await execute_tool_call(tc)

                # 通知前端：工具执行完成
                yield {
                    "type": "tool_end",
                    "tool_name": tool_name,
                    "result": tool_result,
                }

                # 记录历史
                tool_calls_history.append({
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "result": tool_result,
                    "round": round_count,
                })

                # 将工具结果追加到对话消息
                self.llm_service.message.append(
                    ChatMessage(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tc.id,
                    )
                )

            # 再次流式调用 LLM（工具反馈后）
            stream_result = await self._stream_llm_call(
                tools=self.tools_schema if self.tools_schema else None,
                yield_tokens=True,
                add_user_msg=False,
            )

            async for event in stream_result["stream"]:
                yield event

            # 等待生产者完成并读取结果
            await stream_result["_task"]
            result = stream_result["_result"]
            collected_tool_calls = result["tool_calls"]
            full_content = result["full_content"]
            reasoning_content = result["reasoning_content"]
            finish_reason = result["finish_reason"]

        # 最终完成事件
        yield {
            "type": "done",
            "full_content": full_content,
            "tool_calls_history": tool_calls_history,
            "reasoning_content": reasoning_content,
        }

    async def _stream_llm_call(
        self,
        tools: Optional[list[dict]] = None,
        yield_tokens: bool = True,
        add_user_msg: bool = False,
    ) -> dict[str, Any]:
        """执行一次流式 LLM 调用，收集所有 token 和 tool_calls。

        该方法返回一个字典，其中 "stream" 是异步生成器（yield token事件），
        其余字段在流结束后填充完整结果。

        为了同时支持「实时推送 token」和「收集完整结果」，
        使用了内部异步队列 + 后台任务的模式。

        Args:
            tools: 可选的工具定义列表。
            yield_tokens: 是否 yield token 事件。
            add_user_msg: 保留参数（此层不添加用户消息）。

        Returns:
            字典包含:
            - stream: 异步生成器，yield token/reasoning 事件
            - tool_calls: 完成后的 ToolCall 列表
            - full_content: 完整文本内容
            - reasoning_content: 完整推理内容
            - finish_reason: 结束原因
        """
        import asyncio

        # 用队列在流式消费和结果收集之间传递数据
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        # 收集结果的容器
        result_container: dict[str, Any] = {
            "tool_calls": [],
            "full_content": "",
            "reasoning_content": None,
            "finish_reason": None,
        }

        async def _producer() -> None:
            """后台任务：调用流式 API 并将 token 放入队列。"""
            messages = self._build_messages_for_api()
            request_params: dict[str, Any] = {
                "model": self.llm_service.model,
                "messages": messages,
                "stream": True,
            }

            if tools:
                request_params["tools"] = tools

            try:
                stream = await self.llm_service.client.chat.completions.create(
                    **request_params
                )

                full_content = ""
                reasoning_content: Optional[str] = None
                collected_tool_calls: list[dict[str, Any]] = []
                finish_reason = None

                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    # 处理文本内容
                    if delta.content:
                        full_content += delta.content
                        await queue.put({
                            "type": "token",
                            "content": delta.content,
                        })

                    # 处理推理内容
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        if reasoning_content is None:
                            reasoning_content = ""
                        reasoning_content += delta.reasoning_content
                        await queue.put({
                            "type": "reasoning",
                            "content": delta.reasoning_content,
                        })

                    # 处理工具调用（流式累积）
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            while len(collected_tool_calls) <= tc_chunk.index:
                                collected_tool_calls.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": "",
                                    },
                                })
                            if tc_chunk.id:
                                collected_tool_calls[tc_chunk.index]["id"] = tc_chunk.id
                            if tc_chunk.function:
                                if tc_chunk.function.name:
                                    collected_tool_calls[tc_chunk.index]["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    collected_tool_calls[tc_chunk.index]["function"]["arguments"] += tc_chunk.function.arguments

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                # 构建 ToolCall 列表
                tool_calls_data = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=tc["function"],
                    )
                    for tc in collected_tool_calls
                ] if collected_tool_calls else []

                # 将 assistant 消息追加到历史
                self.llm_service.message.append(
                    ChatMessage(
                        role="assistant",
                        content=full_content,
                        tool_calls=tool_calls_data if tool_calls_data else None,
                    )
                )

                # 填充结果容器
                result_container["tool_calls"] = tool_calls_data
                result_container["full_content"] = full_content
                result_container["reasoning_content"] = reasoning_content
                result_container["finish_reason"] = finish_reason

            except Exception as e:
                import traceback
                logger.error(
                    f"流式 LLM 调用失败: {e}\n{traceback.format_exc()}"
                )
            finally:
                # 哨兵值，表示流结束
                await queue.put(None)

        async def _consumer() -> AsyncGenerator[dict[str, Any], None]:
            """从队列中消费 token 事件。"""
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event

        # 启动生产者任务
        producer_task = asyncio.create_task(_producer())

        # 返回流和结果容器
        # 注意：调用者必须先消费完 stream，result_container 才会被填充
        return {
            "stream": _consumer(),
            "tool_calls": result_container["tool_calls"],
            "full_content": result_container["full_content"],
            "reasoning_content": result_container["reasoning_content"],
            "finish_reason": result_container["finish_reason"],
            "_task": producer_task,
            "_result": result_container,
        }
