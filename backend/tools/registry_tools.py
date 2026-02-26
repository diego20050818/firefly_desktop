"""工具注册表模块 - 管理所有 MCP 工具并提供发现与执行能力。

该模块负责:
- 从本地 FastMCP 实例发现已注册的工具
- 从远程 HTTP MCP 服务器获取工具列表
- 提供工具元信息的统一查询接口
- 提供工具执行能力（供 ChatAgent 调用）

编码规范: Google Python Style Guide
"""

import json
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from pydantic import BaseModel


class ToolInfo(BaseModel):
    """工具元信息模型。

    Attributes:
        name: 工具名称，必须全局唯一。
        description: 工具功能描述，供 LLM 理解工具用途。
        parameters: 工具参数的 JSON Schema 定义。
    """

    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = {}


class ToolRegistry:
    """工具注册表 - 统一管理本地与远程 MCP 工具。

    该类维护了一个工具缓存，支持从以下来源发现工具:
    1. 本地 FastMCP 实例（通过直接导入）
    2. 远程 HTTP MCP 服务器（通过 JSON-RPC）

    Attributes:
        mcp_servers: 远程 MCP 服务器 URL 列表。
        tools_cache: 缓存的工具信息列表。
    """

    def __init__(self) -> None:
        """初始化工具注册表。"""
        self.mcp_servers: List[str] = []
        self.tools_cache: List[ToolInfo] = []

    def add_mcp_server(self, url: str) -> None:
        """添加远程 MCP 服务器地址。

        Args:
            url: MCP 服务器的 HTTP 地址。
        """
        if url not in self.mcp_servers:
            self.mcp_servers.append(url)
            logger.info(f"已添加远程 MCP 服务器: {url}")

    async def fetch_tools_from_http_mcp(
        self, server_url: str
    ) -> List[ToolInfo]:
        """从远程 HTTP MCP 服务器获取工具列表。

        通过 JSON-RPC 协议调用 tools/list 方法获取工具定义。

        Args:
            server_url: MCP 服务器的 HTTP 地址。

        Returns:
            该服务器上注册的工具信息列表。
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{server_url}/jsonrpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    tools = []
                    if "result" in data and "tools" in data["result"]:
                        for tool_data in data["result"]["tools"]:
                            tool_info = ToolInfo(
                                name=tool_data.get("name", ""),
                                description=tool_data.get("description", ""),
                                parameters=tool_data.get("inputSchema", {}),
                            )
                            tools.append(tool_info)
                    logger.info(
                        f"从 {server_url} 获取到 {len(tools)} 个工具"
                    )
                    return tools
                else:
                    logger.warning(
                        f"从 {server_url} 获取工具失败: "
                        f"HTTP {response.status_code}"
                    )
                    return []
        except Exception as e:
            logger.warning(f"连接远程 MCP 服务器 {server_url} 失败: {e}")
            return []

    def fetch_tools_from_local_mcp(self) -> List[ToolInfo]:
        """从本地 FastMCP 实例获取已注册的工具列表。

        直接导入 tools.launch_app 中的 FastMCP 实例，
        遍历其内部工具管理器获取工具元信息。

        兼容 FastMCP 2.x 的多种内部 API 结构。

        Returns:
            本地注册的工具信息列表。
        """
        try:
            from .launch_app import mcp

            tools = []

            # 兼容 FastMCP 2.x 的内部 API
            # 优先使用 _tool_manager._tools（FastMCP >= 2.x）
            tool_dict = None
            if hasattr(mcp, "_tool_manager") and hasattr(
                mcp._tool_manager, "_tools"
            ):
                tool_dict = mcp._tool_manager._tools
            elif hasattr(mcp, "_tools"):
                # 旧版 FastMCP 兼容
                tool_dict = mcp._tools
            else:
                logger.warning(
                    "无法访问 FastMCP 内部工具注册表，"
                    "请检查 FastMCP 版本"
                )
                return []

            for tool_name, tool_obj in tool_dict.items():
                # 获取工具描述和参数 schema
                description = getattr(tool_obj, "description", "") or ""
                parameters = getattr(tool_obj, "parameters", None)

                # 尝试多种方式获取 input_schema
                if parameters is None:
                    parameters = getattr(tool_obj, "input_schema", None)
                if parameters is None:
                    parameters = {"type": "object", "properties": {}}

                # 如果 parameters 是 Pydantic model，转换为 dict
                if hasattr(parameters, "model_json_schema"):
                    parameters = parameters.model_json_schema()
                elif hasattr(parameters, "schema"):
                    parameters = parameters.schema()

                tool_info = ToolInfo(
                    name=tool_name,
                    description=description,
                    parameters=parameters,
                )
                tools.append(tool_info)

            logger.info(f"从本地 FastMCP 获取到 {len(tools)} 个工具")
            return tools

        except ImportError as e:
            logger.error(f"导入本地 MCP 模块失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取本地 MCP 工具失败: {e}")
            return []

    async def get_all_tools(self) -> List[ToolInfo]:
        """获取所有来源的工具列表（本地 + 远程 + Stdio）。

        Returns:
            合并后的完整工具信息列表。
        """
        all_tools = []

        # 1. 获取本地工具
        local_tools = self.fetch_tools_from_local_mcp()
        all_tools.extend(local_tools)

        # 2. 获取 HTTP 远程工具
        for server_url in self.mcp_servers:
            remote_tools = await self.fetch_tools_from_http_mcp(server_url)
            all_tools.extend(remote_tools)

        # 3. 获取 Stdio MCP 工具
        try:
            from tools.stdio_mcp import stdio_mcp_manager
            stdio_tools = await stdio_mcp_manager.get_all_tools()
            all_tools.extend(stdio_tools)
        except Exception as e:
            logger.error(f"获取 Stdio MCP 工具失败: {e}")

        # 更新缓存
        self.tools_cache = all_tools
        logger.info(f"工具注册表已更新，共 {len(all_tools)} 个工具")
        return all_tools

    def get_cached_tools(self) -> List[ToolInfo]:
        """获取缓存的工具列表（不触发重新扫描）。

        Returns:
            上次扫描缓存的工具信息列表。
        """
        return self.tools_cache


# 创建全局工具注册表单例
tool_registry = ToolRegistry()