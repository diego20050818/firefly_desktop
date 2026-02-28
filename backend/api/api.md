# Firefly AI API 文档

## 概述

Firefly AI 提供 REST 和 WebSocket API 接口，支持智能对话、工具调用等功能。

## 基础信息

- **基础URL**: `http://localhost:8000`
- **版本**: 0.2.0
- **认证**: 无（开发环境）

## HTTP API

### 健康检查

#### GET `/health`

**描述**: 检查服务健康状态

**响应**:
```json
{
  "status": "ok"
}
智能对话接口
POST /agent/chat
描述: 带自动工具调用的智能对话接口

请求体:

json
{
  "prompt": "用户输入文本",
  "session_id": "会话ID，可选，默认'default'",
  "provider": "LLM提供商，可选，默认'deepseek'"
}
响应:

json
{
  "content": "AI回复内容",
  "tool_calls_history": [
    {
      "tool_name": "工具名",
      "arguments": "工具参数",
      "result": "工具执行结果",
      "round": "执行轮次"
    }
  ],
  "reasoning_content": "推理内容（如果有）",
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 30
  },
  "session_id": "会话ID"
}
POST /agent/stream_chat
描述: 流式智能对话接口（Server-Sent Events）

请求体:

json
{
  "prompt": "用户输入文本",
  "session_id": "会话ID，可选，默认'default'",
  "provider": "LLM提供商，可选，默认'deepseek'"
}
响应: SSE流式数据，每个事件格式:

json
{
  "type": "token|reasoning|tool_start|tool_end|done|error",
  "content": "内容",
  "tool_name": "工具名（当type为tool相关时）",
  "arguments": "工具参数（当type为tool相关时）",
  "result": "工具结果（当type为tool_end时）",
  "full_content": "完整内容（当type为done时）",
  "tool_calls_history": "工具调用历史（当type为done时）",
  "message": "错误信息（当type为error时）"
}
POST /agent/reset
描述: 重置会话历史

查询参数:

session_id: 会话ID，默认'default'
响应:

json
{
  "message": "会话 {session_id} 已重置"
}
工具查询接口
GET /tools/available
描述: 获取所有可用的MCP工具

响应:

json
{
  "tools": [
    {
      "name": "工具名",
      "description": "工具描述",
      "parameters": "参数定义"
    }
  ]
}
WebSocket API
WebSocket 智能对话
WS /ws/agent/chat
描述: WebSocket流式智能对话

客户端发送消息:

json
{
  "type": "user_input|reset|heartbeat",
  "data": {
    "text": "用户输入文本（当type为user_input时）"
  },
  "provider": "LLM提供商，可选，默认'deepseek'"
}
服务端推送消息:

json
{
  "type": "token|reasoning|tool_start|tool_end|done|error|system",
  "content": "内容",
  "tool_name": "工具名（当type为tool相关时）",
  "arguments": "工具参数（当type为tool相关时）",
  "result": "工具结果（当type为tool_end时）",
  "full_content": "完整内容（当type为done时）",
  "tool_calls_history": "工具调用历史（当type为done时）",
  "message": "错误信息或系统消息"
}
错误处理
所有错误都会返回包含 error 字段的JSON对象
WebSocket连接异常会发送 {"type": "error", "message": "错误信息"}
示例
发起对话
bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "你好",
    "session_id": "user_001",
    "provider": "deepseek"
  }'
流式对话
bash
curl -X POST http://localhost:8000/agent/stream_chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "你好",
    "session_id": "user_001",
    "provider": "deepseek"
  }'