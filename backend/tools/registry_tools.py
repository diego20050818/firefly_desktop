"""
工具注册表：管理所有MCP工具并提供API接口
"""
import httpx
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import subprocess
import json
import sys
import os

class ToolInfo(BaseModel):
    """工具信息模型"""
    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = {}

class ToolRegistry:
    """工具注册表"""
    def __init__(self):
        self.mcp_servers = []
        self.tools_cache = []

    def add_mcp_server(self, url: str):
        """添加MCP服务器地址"""
        if url not in self.mcp_servers:
            self.mcp_servers.append(url)

    async def fetch_tools_from_http_mcp(self, server_url: str) -> List[ToolInfo]:
        """从HTTP MCP服务器获取工具列表"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 尝试通过JSON-RPC获取工具列表
                response = await client.post(
                    f"{server_url}/jsonrpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 解析返回的工具列表
                    tools = []
                    if "result" in data and "tools" in data["result"]:
                        for tool_data in data["result"]["tools"]:
                            tool_info = ToolInfo(
                                name=tool_data.get("name", ""),
                                description=tool_data.get("description", ""),
                                parameters=tool_data.get("inputSchema", {})
                            )
                            tools.append(tool_info)
                    
                    return tools
                else:
                    print(f"Failed to fetch tools from {server_url}: {response.status_code}")
                    return []
        except Exception as e:
            print(f"Error fetching tools from {server_url}: {str(e)}")
            return []

    def fetch_tools_from_local_mcp(self) -> List[ToolInfo]:
        """直接从本地MCP模块获取工具列表（推荐方案）"""
        try:
            # 直接导入工具定义
            from .launch_app import mcp
            
            tools = []
            for tool_name, tool_obj in mcp._tools.items():
                tool_info = ToolInfo(
                    name=tool_name,
                    description=getattr(tool_obj, 'description', ''),
                    parameters=getattr(tool_obj, 'input_schema', {})
                )
                tools.append(tool_info)
            
            return tools
        except Exception as e:
            print(f"Error fetching local tools: {str(e)}")
            return []

    async def get_all_tools(self) -> List[ToolInfo]:
        """获取所有MCP服务器的工具列表"""
        all_tools = []
        
        # 先尝试获取本地工具
        local_tools = self.fetch_tools_from_local_mcp()
        all_tools.extend(local_tools)
        
        # 再尝试从远程HTTP服务获取工具
        for server_url in self.mcp_servers:
            tools = await self.fetch_tools_from_http_mcp(server_url)
            all_tools.extend(tools)
        
        # 更新缓存
        self.tools_cache = all_tools
        return all_tools

    def get_cached_tools(self) -> List[ToolInfo]:
        """获取缓存的工具列表"""
        return self.tools_cache

# 创建全局工具注册表实例
tool_registry = ToolRegistry()

# 注册HTTP MCP服务器地址（如果有的话）
tool_registry.add_mcp_server("http://localhost:3000")