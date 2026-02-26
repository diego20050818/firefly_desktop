import asyncio
import json
import httpx
from typing import Optional


class VoiceChatTerminal:
    def __init__(self):
        self.session_id = "terminal_test_01"
        self.provider = "deepseek"
        self.base_url = "http://localhost:8000"
        self.stream_chat_url = f"{self.base_url}/agent/stream_chat"
        self.stt_transcribe_url = f"{self.base_url}/stt/transcribe"
        self.client = httpx.AsyncClient(timeout=300)
        self.voice_mode = False  # 语音模式开关

    async def run(self):
        """启动终端交互"""
        self.print_welcome_message()
        
        try:
            while True:
                user_input = await self.get_user_input()
                
                if user_input.lower() == "exit":
                    break
                elif user_input.lower() == "reset":
                    await self.handle_reset()
                elif user_input.lower() == "speak":
                    self.voice_mode = True
                    print("[语音模式]: 已开启语音输入模式，接下来请输入任意内容开始语音识别")
                elif user_input.lower() == "speakend":
                    self.voice_mode = False
                    print("[语音模式]: 已关闭语音输入模式")
                else:
                    # 根据当前模式决定如何处理输入
                    if self.voice_mode:
                        # 语音模式下进入自动循环：识别 -> 处理 -> 识别
                        # 这里的 user_input 只是触发器，循环在内部进行
                        while self.voice_mode:
                            print("\n[语音模式]: 正在等待说话...")
                            transcription = await self.speech_to_text_vad()
                            if transcription.strip():
                                print(f"[已识别]: {transcription}")
                                await self.send_to_ai(transcription)
                            else:
                                print("[语音模式]: 未检测到有效输入，继续等待...")
                                await asyncio.sleep(1) # 避免由于超时导致的过度频繁请求
                        else:
                            # 如果 voice_mode 在循环中被关闭（例如通过其他方式，虽然此处暂未实现）
                            pass
                    else:
                        await self.send_to_ai(user_input)
        finally:
            await self.client.aclose()

    def print_welcome_message(self):
        """打印欢迎信息"""
        print("="*50)
        print("      Firefly API 多轮对话流式测试终端      ")
        print(f"  请求地址: {self.stream_chat_url}")
        print(f"  Session ID: {self.session_id}")
        print("  (输入 'exit' 退出程序)")
        print("  (输入 'reset' 重置对话)")
        print("  (输入 'speak' 开启连续语音输入)")
        print("  (输入 'speakend' 关闭连续语音输入)")
        print("="*50 + "\n")

    async def get_user_input(self) -> str:
        """获取用户输入"""
        if self.voice_mode:
            # 语音模式下，我们只需等待第一次触发，之后进入自动循环
            # 如果想退出语音模式，可以在这里检测特定输入
            u = input("\n[语音模式活跃] 输入 'speakend' 关闭，或按回车开始自动识别: ").strip()
            if u.lower() == "speakend":
                self.voice_mode = False
                return "speakend"
            return "dummy"
        else:
            return input("\n[USER]: ").strip()

    async def handle_reset(self):
        """处理重置命令"""
        resp = await self.client.post(
            f"{self.base_url}/agent/reset",
            params={"session_id": self.session_id}
        )
        print(f"系统: {resp.json().get('message')}")

    async def speech_to_text_vad(self) -> str:
        """使用 VAD 智能识别语音"""
        url = f"{self.base_url}/stt/transcribe_vad"
        try:
            resp = await self.client.post(url)
            if resp.status_code == 200:
                return resp.json().get("transcription", "")
            else:
                print(f"[语音识别失败]: {resp.status_code}")
                return ""
        except Exception as e:
            print(f"[语音识别错误]: {e}")
            return ""

    async def speech_to_text(self, duration: int = 5) -> str:
        """语音转文字 (固定时长)"""
        # 保留原方法作为备选
        try:
            transcribe_resp = await self.client.post(
                self.stt_transcribe_url,
                params={"duration": duration}
            )
            
            if transcribe_resp.status_code == 200:
                return transcribe_resp.json().get("transcription", "")
            return ""
        except Exception:
            return ""

    async def send_to_ai(self, user_input: str):
        """发送输入到AI并显示结果"""
        payload = {
            "prompt": user_input,
            "session_id": self.session_id,
            "provider": self.provider
        }

        print("[AGENT]: ", end="", flush=True)

        try:
            async with self.client.stream('POST', self.stream_chat_url, json=payload) as response:
                if response.status_code != 200:
                    print(f"\n[请求失败] 状态码: {response.status_code}")
                    text = await response.aread()
                    print(text.decode('utf-8'))
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                        
                    data_str = line[6:].strip()  # 去掉 "data: " 前缀
                    if not data_str:
                        continue
                        
                    try:
                        event = json.loads(data_str)
                        await self.handle_event(event)
                    except json.JSONDecodeError:
                        # 忽略非 JSON 结构的无效截断
                        print(f"[调试信息]: 无法解析的事件数据: {data_str}")
                        pass

            print()  # 此轮输出结束，换行

        except Exception as e:
            print(f"\n[AI通信错误]: {e}")

    async def handle_event(self, event: dict):
        """处理从AI返回的各种事件"""
        event_type = event.get("type")

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


async def main():
    terminal = VoiceChatTerminal()
    await terminal.run()


if __name__ == "__main__":
    asyncio.run(main())
