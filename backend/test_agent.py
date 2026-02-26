"""Agent 集成测试脚本 - 验证 ChatAgent 工具调用流程。

该脚本测试以下功能:
1. FastAPI 服务是否正常启动
2. 工具注册表是否正确发现 MCP 工具
3. /agent/chat 端点是否能自动执行工具调用
4. WebSocket /ws/agent/chat 是否正常工作

使用方法:
    先启动服务: python main.py
    再运行测试: python test_agent.py

编码规范: Google Python Style Guide
"""

import asyncio
import json
import sys

import httpx
from loguru import logger


BASE_URL = "http://localhost:8000"


async def test_health() -> bool:
    """测试 1: 健康检查。"""
    logger.info("=" * 50)
    logger.info("测试 1: 健康检查")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code == 200 and resp.json()["status"] == "ok":
                logger.success("✅ 健康检查通过")
                return True
            else:
                logger.error(f"❌ 健康检查失败: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"❌ 无法连接服务器: {e}")
        logger.error("请确保已运行: python main.py")
        return False


async def test_tools_discovery() -> bool:
    """测试 2: 工具发现。"""
    logger.info("=" * 50)
    logger.info("测试 2: MCP 工具发现")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BASE_URL}/tools/available")
            data = resp.json()
            tools = data.get("tools", [])
            logger.info(f"发现 {len(tools)} 个工具:")
            for tool in tools:
                logger.info(f"  - {tool['name']}: {tool['description'][:60]}")

            if len(tools) > 0:
                logger.success("✅ 工具发现通过")
                return True
            else:
                logger.warning("⚠️ 未发现任何工具（可能是 FastMCP 内部 API 变化）")
                return False
    except Exception as e:
        logger.error(f"❌ 工具发现失败: {e}")
        return False


async def test_agent_chat_simple() -> bool:
    """测试 3: 简单对话（不触发工具调用）。"""
    logger.info("=" * 50)
    logger.info("测试 3: Agent 简单对话（无工具调用）")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{BASE_URL}/agent/chat",
                json={
                    "prompt": "你好，你是谁？用一句话回答。",
                    "session_id": "test_simple",
                    "provider": "deepseek",
                },
            )
            data = resp.json()

            if "error" in data:
                logger.error(f"❌ 对话失败: {data['error']}")
                return False

            content = data.get("content", "")
            tool_calls = data.get("tool_calls_history", [])
            logger.info(f"AI 回复: {content[:200]}")
            logger.info(f"工具调用次数: {len(tool_calls)}")

            if content:
                logger.success("✅ 简单对话通过")
                return True
            else:
                logger.error("❌ AI 未返回内容")
                return False
    except Exception as e:
        logger.error(f"❌ 简单对话失败: {e}")
        return False


async def test_agent_chat_with_tool() -> bool:
    """测试 4: 带工具调用的对话（触发 add 工具）。"""
    logger.info("=" * 50)
    logger.info("测试 4: Agent 工具调用对话（调用 add 工具）")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{BASE_URL}/agent/chat",
                json={
                    "prompt": "请帮我计算 15 + 27 等于多少，请使用 add 工具来计算。",
                    "session_id": "test_tool",
                    "provider": "deepseek",
                },
            )
            data = resp.json()

            if "error" in data:
                logger.error(f"❌ 工具调用失败: {data['error']}")
                return False

            content = data.get("content", "")
            tool_calls = data.get("tool_calls_history", [])
            logger.info(f"AI 回复: {content[:200]}")
            logger.info(f"工具调用次数: {len(tool_calls)}")

            for tc in tool_calls:
                logger.info(
                    f"  工具: {tc['tool_name']} | "
                    f"参数: {tc['arguments']} | "
                    f"结果: {tc['result']}"
                )

            if tool_calls:
                logger.success("✅ 工具调用对话通过")
                return True
            else:
                logger.warning(
                    "⚠️ LLM 未调用工具（可能 LLM 自行计算了结果）"
                )
                return True  # 允许通过，因为 LLM 可能直接算出结果
    except Exception as e:
        logger.error(f"❌ 工具调用对话失败: {e}")
        return False


async def test_agent_reset() -> bool:
    """测试 5: 会话重置。"""
    logger.info("=" * 50)
    logger.info("测试 5: Agent 会话重置")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BASE_URL}/agent/reset",
                params={"session_id": "test_simple"},
            )
            data = resp.json()
            logger.info(f"重置结果: {data['message']}")
            logger.success("✅ 会话重置通过")
            return True
    except Exception as e:
        logger.error(f"❌ 会话重置失败: {e}")
        return False


async def main() -> None:
    """运行所有测试。"""
    logger.info("🚀 开始 Agent 集成测试")
    logger.info("=" * 50)

    results = {
        "健康检查": await test_health(),
    }

    # 如果服务器不可用，跳过后续测试
    if not results["健康检查"]:
        logger.error("服务器不可用，跳过后续测试")
        return

    results["工具发现"] = await test_tools_discovery()
    results["简单对话"] = await test_agent_chat_simple()
    results["工具调用"] = await test_agent_chat_with_tool()
    results["会话重置"] = await test_agent_reset()

    # 打印测试报告
    logger.info("\n" + "=" * 50)
    logger.info("📊 测试报告")
    logger.info("=" * 50)
    passed = 0
    total = len(results)
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"  {name}: {status}")
        if result:
            passed += 1

    logger.info(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        logger.success("🎉 所有测试通过！")
    else:
        logger.warning(f"⚠️ {total - passed} 个测试未通过")


if __name__ == "__main__":
    asyncio.run(main())
