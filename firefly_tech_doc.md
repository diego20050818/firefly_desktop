# Firefly AI 桌宠后端技术文档

> **版本**: 0.2.0  
> **更新日期**: 2026-02-25  
> **核心架构**: FastAPI + DeepSeek ToolCalls + FastMCP

---

## 一、系统架构总览

```
用户消息
    │
    ▼
┌──────────────────────────────────────────────┐
│         FastAPI  (api/app.py)                 │
│  ┌────────────────┐  ┌─────────────────────┐ │
│  │  /agent/chat   │  │  /ws/agent/chat     │ │
│  │  (REST 端点)   │  │  (WebSocket 端点)   │ │
│  └───────┬────────┘  └──────────┬──────────┘ │
│          └──────────┬───────────┘             │
│                     ▼                         │
│          ┌──────────────────┐                 │
│          │    ChatAgent     │                 │
│          │ (service/agent.py)│                │
│          └────────┬─────────┘                 │
│                   │                           │
│       ┌───────────┼───────────┐               │
│       ▼           ▼           ▼               │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐    │
│  │DeepSeek │ │ToolExec │ │  Messages   │    │
│  │  LLM    │ │  MCP    │ │  History    │    │
│  └─────────┘ └─────────┘ └─────────────┘    │
│                   │                           │
│       ┌───────────┼───────────┐               │
│       ▼           ▼           ▼               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │  add    │ │open_app │ │ ...更多  │        │
│  │ (MCP)   │ │  (MCP)  │ │  工具   │        │
│  └─────────┘ └─────────┘ └─────────┘        │
└──────────────────────────────────────────────┘
```

---

## 二、核心文件说明

| 文件路径 | 功能 | 重要程度 |
|---|---|---|
| `service/agent.py` | **核心 Agent 引擎** - 编排 LLM 对话与工具调用循环 | ⭐⭐⭐ |
| `api/app.py` | FastAPI 路由定义 - REST + WebSocket 端点 | ⭐⭐⭐ |
| `tools/registry_tools.py` | 工具注册表 - 发现和管理 MCP 工具 | ⭐⭐ |
| `tools/launch_app.py` | 本地 FastMCP 工具实例（add、open_application） | ⭐⭐ |
| `service/llm_service.py` | LLM 服务抽象基类 - 消息格式转换 | ⭐⭐ |
| `service/deepseek.py` | DeepSeek API 对接实现 | ⭐⭐ |
| `service/llm_register.py` | LLM 服务提供商注册中心 | ⭐ |
| `main.py` | 程序入口 - 启动 FastAPI + FastMCP | ⭐ |
| `data/config.yaml` | 全局配置文件（API Key、模型参数） | ⭐ |

---

## 三、工具调用流程详解

### 3.1 DeepSeek ToolCalls 消息格式

遵循 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/guides/tool_calls) 的要求：

```python
# 步骤 1: 用户消息 + 工具定义 -> LLM
messages = [
    {"role": "system", "content": "你是流萤..."},
    {"role": "user", "content": "帮我算 15 + 27"}
]
tools = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "将两个数字相加",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "第一个数字"},
                    "b": {"type": "integer", "description": "第二个数字"}
                },
                "required": ["a", "b"]
            }
        }
    }
]

# 步骤 2: LLM 返回 tool_calls（finish_reason='tool_calls'）
# response.tool_calls = [{"id": "xxx", "function": {"name": "add", "arguments": '{"a": 15, "b": 27}'}}]

# 步骤 3: 执行工具，将结果追加为 role='tool' 消息
messages.append({"role": "assistant", "content": "", "tool_calls": [...]})
messages.append({"role": "tool", "tool_call_id": "xxx", "content": "42"})

# 步骤 4: 再次调用 LLM，获取自然语言回复
# response.content = "15 + 27 = 42"
```

### 3.2 ChatAgent 自动化循环

`ChatAgent.chat()` 方法自动处理上述流程：

```
用户输入
    │
    ▼
ChatAgent.chat("帮我算 15+27")
    │
    ├─ 1. 构建 tools schema（从 MCP 注册表获取）
    ├─ 2. 调用 DeepSeek API（附带 tools）
    │
    ▼ finish_reason == "tool_calls"?
   ┌──┐
   │是│──→ 3. 解析 tool_calls
   └──┘    4. execute_tool_call(tool_call) → 调用 FastMCP 工具
           5. 将结果追加为 role='tool' 消息
           6. 再次调用 LLM（回到步骤 2）
   ┌──┐
   │否│──→ 返回最终 AI 回复
   └──┘
```

最大循环轮数由 `max_tool_rounds` 控制（默认 5），防止死循环。

---

## 四、API 接口文档

### 4.1 REST API

#### `POST /agent/chat` ⭐ 推荐

智能对话接口，自动处理工具调用。

**请求体:**
```json
{
    "prompt": "帮我计算 15 + 27",
    "session_id": "user_001",
    "provider": "deepseek"
}
```

**响应:**
```json
{
    "content": "15 + 27 = 42",
    "tool_calls_history": [
        {
            "tool_name": "add",
            "arguments": "{\"a\": 15, \"b\": 27}",
            "result": "42",
            "round": 1
        }
    ],
    "reasoning_content": null,
    "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    "session_id": "user_001"
}
```

#### `POST /agent/reset`

重置对话历史。

```
POST /agent/reset?session_id=user_001
```

#### `POST /chat/{provider}`

基础 LLM 对话（无自动工具调用，保留兼容）。

#### `GET /tools/available`

列出所有可用的 MCP 工具。

#### `GET /health`

健康检查。

### 4.2 WebSocket API

#### `ws://localhost:8000/ws/agent/chat` ⭐ 推荐

**客户端发送:**
```json
{
    "type": "user_input",
    "data": {"text": "帮我打开记事本"},
    "provider": "deepseek"
}
```

**服务端推送 (按顺序):**
```json
// 1. 正在思考
{"type": "system_action", "data": {"action": "thinking", "status": "started"}}

// 2. 工具调用状态（如果有）
{"type": "tool_calling", "data": {"tool": "open_application", "status": "completed", "result": "..."}}

// 3. AI 最终回复
{"type": "ai_response", "data": {"text": "已经帮你打开了记事本~", "emotion": "neutral"}}
```

---

## 五、添加新的 MCP 工具

### 5.1 在 `tools/launch_app.py` 中注册

```python
from tools.launch_app import mcp

@mcp.tool
def your_new_tool(param1: str, param2: int) -> str:
    """工具描述 - 会被 LLM 用来理解工具用途。

    Args:
        param1: 参数1的描述。
        param2: 参数2的描述。

    Returns:
        工具执行结果字符串。
    """
    # 实现工具逻辑
    return f"执行结果: {param1}, {param2}"
```

### 5.2 工具自动发现机制

注册新工具后，**无需修改其他文件**。ChatAgent 通过以下链路自动发现：

```
@mcp.tool → FastMCP._tool_manager._tools
    → ToolRegistry.fetch_tools_from_local_mcp()
    → convert_mcp_tools_to_openai_schema()
    → ChatAgent.tools_schema
    → DeepSeek API tools 参数
```

重启服务即可生效。

---

## 六、配置说明

### 6.1 `data/config.yaml`

```yaml
# 基本设置
your_name: diego
chat_bot_name: 流萤
temperature: 0.3
stream: True
thinking: True              # 启用 DeepSeek 思考模式
history_dir: E:\firefly_desktop\history

# 人格化 System Prompt
system_prompt: |
  你是流萤，星核猎手的成员...

# LLM 提供商
default_provider: "deepseek"
providers:
  deepseek:
    enabled: true
    api_key: "sk-xxxx"
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
```

### 6.2 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `thinking` | `True` | 是否启用 DeepSeek 思考模式（推理内容） |
| `temperature` | `0.3` | LLM 创造性参数（0-1） |
| `max_tool_rounds` | `5` | ChatAgent 单次对话最大工具调用轮数 |

---

## 七、快速开始

### 7.1 启动服务

```bash
cd backend
python main.py
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

### 7.2 运行测试

```bash
cd backend
python test_agent.py
```

### 7.3 快速验证工具调用

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "帮我计算 100 + 200", "session_id": "test"}'
```

---

## 八、项目结构

```
backend/
├── main.py                    # 程序入口
├── test_agent.py              # Agent 集成测试
├── pyproject.toml             # Python 依赖管理
│
├── api/
│   ├── __init__.py
│   └── app.py                 # FastAPI 路由定义
│
├── service/
│   ├── __init__.py
│   ├── agent.py               # 🆕 ChatAgent 核心引擎
│   ├── llm_service.py         # LLM 抽象基类
│   ├── llm_register.py        # 服务注册中心
│   └── deepseek.py            # DeepSeek 实现
│
├── tools/
│   ├── __init__.py
│   ├── launch_app.py          # FastMCP 工具定义
│   ├── registry_tools.py      # 工具注册表
│   └── Tool_implementation/
│       ├── launch_app.md      # 设计文档
│       └── launch_software.py # 高级启动器（参考）
│
├── data/
│   └── config.yaml            # 全局配置
│
└── static/                    # 静态资源
```

---

## 九、后续开发建议

1. **流式工具调用**: 当前 Agent 是非流式的（等待完整响应），可改为流式以提升体验
2. **多 MCP Server**: 支持连接多个远程 MCP Server（registry_tools 已预留接口）
3. **工具权限**: 对高危工具（如 `run_command`）增加用户确认机制
4. **RAG 集成**: 将 LlamaIndex 知识库作为一个 MCP 工具，实现知识问答
5. **情感分析**: 根据对话内容分析情绪，驱动 Live2D 表情动画
