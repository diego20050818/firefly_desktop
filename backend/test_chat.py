import asyncio
import json
import httpx

async def main():
    session_id = "terminal_test_01"
    provider = "deepseek"
    url = "http://localhost:8000/agent/stream_chat"

    print("="*50)
    print("      Firefly API 多轮对话流式测试终端      ")
    print(f"  请求地址: {url}")
    print(f"  Session ID: {session_id}")
    print("  (输入 'exit' 退出程序，输入 'reset' 重置对话)")
    print("="*50 + "\n")

    async with httpx.AsyncClient(timeout=300) as client:
        while True:
            try:
                user_input = input("\n[USER]: ").strip()
                if not user_input:
                    continue
                if user_input.lower() == "exit":
                    break
                elif user_input.lower() == "reset":
                    # 发送重置请求
                    resp = await client.post(
                        "http://localhost:8000/agent/reset",
                        params={"session_id": session_id}
                    )
                    print(f"系统: {resp.json().get('message')}")
                    continue

                payload = {
                    "prompt": user_input,
                    "session_id": session_id,
                    "provider": provider
                }

                print("[AGENT]: ", end="", flush=True)

                # 以流式(Stream)方式发送 POST 请求
                async with client.stream('POST', url, json=payload) as response:
                    if response.status_code != 200:
                        print(f"\n[请求失败] 状态码: {response.status_code}")
                        text = await response.aread()
                        print(text.decode('utf-8'))
                        continue

                    # 逐行读取 SSE (Server-Sent Events)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                            
                        data_str = line[6:].strip() # 去掉 "data: " 前缀
                        if not data_str:
                            continue
                            
                        try:
                            event = json.loads(data_str)
                            event_type = event.get("type")

                            # ===================== 解析各种事件类型 =====================
                            if event_type == "token":
                                # 正常的内容回复
                                print(event.get("content", ""), end="", flush=True)
                                
                            elif event_type == "reasoning":
                                # 模型深度思考的中间输出（用灰色字显示）
                                content = event.get('content', '')
                                print(f"\033[90m{content}\033[0m", end="", flush=True)
                                
                            elif event_type == "tool_start":
                                # 提示工具开始执行（黄色背景）
                                tool_name = event.get("tool_name", "")
                                args = event.get("arguments", "")
                                print(f"\n\033[1;33m[🔄 工具调用执行中: {tool_name}({args})]\033[0m\n", end="", flush=True)
                                
                            elif event_type == "tool_end":
                                # 提示工具执行完毕（绿色显示）
                                tool_name = event.get("tool_name", "")
                                result = event.get("result", "")
                                # 截断太长的结果以便终端查看
                                if len(result) > 200:
                                    result = result[:200] + "...(truncated)"
                                print(f"\033[1;32m[✅ 工具 {tool_name} 执行完毕. 结果: {result}]\033[0m\n", end="", flush=True)
                                print("[AGENT 继续回复]: ", end="", flush=True)

                            elif event_type == "done":
                                # 整体回答完成事件
                                pass 
                            
                            elif event_type == "error":
                                print(f"\n\033[1;31m[发生错误]: {event.get('message')}\033[0m")
                                
                        except json.JSONDecodeError:
                            # 忽略非 JSON 结构的无效截断
                            pass

                print() # 此轮输出结束，换行

            except KeyboardInterrupt:
                print("\n[用户中断请求]")
                continue
            except Exception as e:
                print(f"\n[系统错误]: {e}")

if __name__ == "__main__":
    asyncio.run(main())
