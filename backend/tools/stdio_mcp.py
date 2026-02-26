"""Stdio MCP 服务器管理模块 - 管理外部 MCP 服务器的生命周期。

该模块负责:
- 加载 data/mcp.json 配置的 MCP 服务器列表
- 启动子进程 (stdio 模式) 并建立 MCP 客户端会话
- 提取工具元信息
- 提供工具调用接口

编码规范: Google Python Style Guide
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.registry_tools import ToolInfo


class StdioMCPManager:
    """管理通过 Stdio 运行的外部 MCP 服务器。

    该类读取 mcp.json 并为每个服务器创建一个后台进程及 ClientSession。
    它不仅提供发现工具列表的功能，还直接处理代理发起的工具执行请求。

    Attributes:
        config_path: mcp.json 配置文件的路径。
        servers: 已连接的服务器信息，保存 session 等上下文。
        exit_stack: 用于管理所有上下文管理器的退出栈。
    """

    def __init__(self, config_path: str = "../data/mcp.json") -> None:
        """初始化 StdioMCPManager。

        Args:
            config_path: mcp.json 配置文件的相对或绝对路径。
        """
        self.config_path = config_path
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.exit_stack = AsyncExitStack()

    def _load_config(self) -> Dict[str, Any]:
        """加载 MCP 服务器配置。"""
        if not os.path.exists(self.config_path):
            logger.info(f"MCP 配置文件不存在: {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    return {}
                return json.loads(content)
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return {}

    async def initialize(self) -> None:
        """初始化所有配置的 MCP 服务器环境。

        遍历配置，使用 mcp.client.stdio.stdio_client 启动子进程，
        并建立 ClientSession 供后续使用。
        """
        config = self._load_config()
        mcp_servers_config = config.get("mcpServers", {})

        if not mcp_servers_config:
            logger.info("未发现外部 Stdio MCP 服务器配置")
            return

        for server_name, server_details in mcp_servers_config.items():
            command = server_details.get("command")
            args = server_details.get("args", [])
            env = server_details.get("env", None)

            if not command:
                logger.warning(
                    f"跳过服务器 {server_name}: 未提供 command"
                )
                continue

            try:
                logger.info(
                    f"正在启动 MCP 服务器: {server_name} "
                    f"({command} {' '.join(args)})"
                )

                # 将当前环境变量传递下去以防止找不到命令（尤其是 npx，uvx 等）
                env_kwargs = {}
                if env:
                    merged_env = os.environ.copy()
                    merged_env.update(env)
                    # 确保传递给子进程的都是字符串
                    env_kwargs["env"] = {
                        k: str(v) for k, v in merged_env.items()
                    }
                else:
                    env_kwargs["env"] = os.environ.copy()

                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    **env_kwargs
                )

                # 使用 AsyncExitStack 管理生命周期，保持连接常驻
                stdio_transport = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                read_stream, write_stream = stdio_transport

                session = await self.exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )

                # 初始化服务端能力协商
                await session.initialize()

                self.servers[server_name] = {
                    "session": session,
                    "config": server_details,
                    "tools": [],
                }

                logger.info(f"成功连接至 MCP 服务器: {server_name}")

            except Exception as e:
                import traceback
                logger.error(
                    f"初始化 MCP 服务器 {server_name} 失败: {e}\n"
                    f"{traceback.format_exc()}"
                )

    async def get_all_tools(self) -> List[ToolInfo]:
        """从所有已连接的 Stdio MCP 服务器获取工具列表。

        Returns:
            所有服务器提供的工具信息列表。
            如果多个服务器提供了同名工具，后访问的可能会被 Agent 注意到，
            但在调度时需要我们做隔离或者重命名。
            为了简单，先按原名注册，如果冲突需要自行管理。
        """
        all_tools = []
        for server_name, context in self.servers.items():
            session: ClientSession = context["session"]
            try:
                response = await session.list_tools()
                context["tools"] = []
                for tool in response.tools:
                    # 将 mcp-sdk 提供的 tool schema 转换成我们需要内部 ToolInfo
                    # tool.inputSchema 就是 JSON schema
                    tool_info = ToolInfo(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=tool.inputSchema,
                    )
                    all_tools.append(tool_info)
                    context["tools"].append(tool.name)

                logger.info(
                    f"从服务器 {server_name} 成功拉取 "
                    f"{len(response.tools)} 个工具"
                )

            except Exception as e:
                logger.error(
                    f"向服务器 {server_name} 拉取工具失败: {e}"
                )

        return all_tools

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """向包含目标工具的服务器发起调用。

        Args:
            tool_name: 要调用的工具名称。
            arguments: 解析后的工具参数字典。

        Returns:
            执行结果（通常为列表或字符串）。

        Raises:
            ValueError: 若未找到拥有该工具的服务器。
            Exception: 若工具执行失败。
        """
        target_server_name = None
        target_session = None

        # 查找哪个服务器注册了这个工具
        for server_name, context in self.servers.items():
            if tool_name in context.get("tools", []):
                target_server_name = server_name
                target_session = context["session"]
                break

        if not target_session:
            raise ValueError(
                f"在任何 Stdio MCP 服务器中均未发现工具: {tool_name}"
            )

        logger.info(
            f"分发工具调用 {tool_name} 给 {target_server_name}"
        )

        try:
            # mcp.client.session.ClientSession.call_tool
            result = await target_session.call_tool(tool_name, arguments)
            
            # 提取执行结果
            # result 具有 content 属性，其中可能包含文本
            if hasattr(result, "content") and result.content:
                result_str = "\n".join(
                    item.text
                    for item in result.content
                    if hasattr(item, "text")
                )
                return result_str
            else:
                return str(result)
        except Exception as e:
            logger.error(
                f"在服务器 {target_server_name} 执行 {tool_name} 失败: {e}"
            )
            raise

    async def cleanup(self) -> None:
        """关闭所有通信流及会话资源。"""
        logger.info("清理 Stdio MCP 服务器资源...")
        await self.exit_stack.aclose()
        self.servers.clear()

# 全局的 StdioMCP 管理器实例（将在启动时由 app 或 agent 初始化）
stdio_mcp_manager = StdioMCPManager()
