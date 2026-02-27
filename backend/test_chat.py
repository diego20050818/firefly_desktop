import asyncio
import json
import httpx
from voice.tts_service import tts_service

# ✅ 探测 main.py 已启动的 genie 服务器
tts_service.connect_to_existing_server()

class VoiceChatTerminal:
    def __init__(self):
        self.session_id = "terminal_test_01"
        self.provider = "deepseek"
        self.base_url = "http://localhost:8000"
        self.stream_chat_url = f"{self.base_url}/agent/stream_chat"
        self.stt_transcribe_url = f"{self.base_url}/stt/transcribe"
        self.client = httpx.AsyncClient(timeout=300)
        
        self.voice_mode = False
        self.tts_enabled = True

        # ── 增强版防回声门控 ──────────────────────────────────────────────
        # True 表示当前可以录音；False 表示 TTS 物理占用中
        self._tts_idle = asyncio.Event()
        self._tts_idle.set()
        
        # 硬件冷却时间（秒）：防止喇叭余响被 STT 误识别
        # 如果仍有回声，可微调至 0.8
        self.TTS_POST_PLAY_SILENCE = 1

        # 流式 TTS 句子缓冲触发字符
        self.SENTENCE_END_CHARS = frozenset("。！？!?\n")

        # ── 核心流水线队列 ──────────────────────────────────────────────
        self._text_queue = asyncio.Queue()   # 待合成的文本 (str)
        self._audio_queue = asyncio.Queue()  # 已合成的音频 (bytes)
        self._worker_tasks = []

    # ------------------------------------------------------------------ #
    #  生命周期管理                                                       #
    # ------------------------------------------------------------------ #
    async def run(self):
        self._worker_tasks = [
            asyncio.create_task(self._synthesis_worker()),
            asyncio.create_task(self._playback_worker())
        ]

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
                    print("[模式]: 连续语音识别已开启")
                elif user_input.lower() == "speakend":
                    self.voice_mode = False
                    print("[模式]: 语音模式已关闭")
                elif user_input.lower() == "tts":
                    self.tts_enabled = not self.tts_enabled
                    print(f"[模式]: TTS 已{'开启' if self.tts_enabled else '关闭'}")
                else:
                    if self.voice_mode:
                        while self.voice_mode:
                            transcription = await self.speech_to_text_vad()
                            if transcription.strip():
                                print(f"[已识别]: {transcription}")
                                await self.send_to_ai(transcription)
                            else:
                                await asyncio.sleep(0.5)
                    else:
                        await self.send_to_ai(user_input)
        finally:
            for task in self._worker_tasks:
                task.cancel()
            await self.client.aclose()

    # ------------------------------------------------------------------ #
    #  Worker 1: 文本 -> 音频 (合成层)                                    #
    # ------------------------------------------------------------------ #
    async def _synthesis_worker(self):
        while True:
            item = await self._text_queue.get()
            try:
                if isinstance(item, asyncio.Event):
                    await self._audio_queue.put(item)
                else:
                    audio = await tts_service.fetch_audio_bytes(item)
                    if audio:
                        await self._audio_queue.put(audio)
            except Exception as e:
                print(f"\n[合成错误]: {e}")
            finally:
                self._text_queue.task_done()

    # ------------------------------------------------------------------ #
    #  Worker 2: 音频 -> 扬声器 (播放层) —— 修复回声核心                   #
    # ------------------------------------------------------------------ #
    async def _playback_worker(self):
        loop = asyncio.get_event_loop()
        while True:
            item = await self._audio_queue.get()
            try:
                # ── 修复 1：立即锁定 ──
                # 只要队列里有音频或结束信号，立即锁定 STT，防止首个 Token 漏掉
                self._tts_idle.clear() 

                if isinstance(item, asyncio.Event):
                    # ── 修复 2：物理静默缓冲 ──
                    # 收到回合结束标记，等待物理余响消失
                    await asyncio.sleep(self.TTS_POST_PLAY_SILENCE)
                    self._tts_idle.set()
                    item.set() 
                else:
                    # 播放音频
                    await loop.run_in_executor(None, tts_service.play_audio_bytes, item)
            except Exception as e:
                print(f"\n[播放错误]: {e}")
                self._tts_idle.set()
            finally:
                self._audio_queue.task_done()

    # ------------------------------------------------------------------ #
    #  AI 发送逻辑 —— 增强 Buffer Flush                                   #
    # ------------------------------------------------------------------ #
    async def send_to_ai(self, user_input: str) -> str:
        payload = {"prompt": user_input, "session_id": self.session_id, "provider": self.provider}
        print("[AGENT]: ", end="", flush=True)
        
        ai_response = ""
        tts_buf = ""
        turn_done_event = asyncio.Event()

        try:
            async with self.client.stream('POST', self.stream_chat_url, json=payload) as response:
                if response.status_code != 200:
                    print(f"\n[错误]: {response.status_code}")
                    return ""

                async for line in response.aiter_lines():
                    if not line.startswith("data: "): continue
                    data_str = line[6:].strip()
                    if not data_str: continue

                    try:
                        event = json.loads(data_str)
                        token = await self.handle_event(event)
                        ai_response += token

                        if event.get("type") == "token" and token:
                            tts_buf += token
                            if any(c in self.SENTENCE_END_CHARS for c in token):
                                text_to_send = tts_buf.strip()
                                if text_to_send and self.tts_enabled:
                                    self._text_queue.put_nowait(text_to_send)
                                tts_buf = ""
                    except json.JSONDecodeError:
                        continue

            # ── 修复 3：强制 Flush 最后一句 ──
            final_text = tts_buf.strip()
            if final_text and self.tts_enabled:
                self._text_queue.put_nowait(final_text)

            print() 

        except Exception as e:
            print(f"\n[通信错误]: {e}")
        finally:
            # ── 修复 4：双重阻塞确认 ──
            self._text_queue.put_nowait(turn_done_event)
            # 等待播放逻辑完成
            await turn_done_event.wait()
            # 额外等待物理锁回归 set 状态
            await self._tts_idle.wait()

        return ai_response

    # ------------------------------------------------------------------ #
    #  STT & 辅助方法                                                     #
    # ------------------------------------------------------------------ #
    async def speech_to_text_vad(self) -> str:
        # 严防死守：TTS 没静默前绝不请求 STT
        if not self._tts_idle.is_set():
            await self._tts_idle.wait()
        
        url = f"{self.base_url}/stt/transcribe_vad"
        try:
            resp = await self.client.post(url, timeout=60)
            return resp.json().get("transcription", "") if resp.status_code == 200 else ""
        except:
            return ""

    async def get_user_input(self) -> str:
        if self.voice_mode:
            return "dummy" 
        return input("\n[USER]: ").strip()

    async def handle_event(self, event: dict) -> str:
        etype = event.get("type")
        content = event.get("content", "")
        if etype == "token":
            print(content, end="", flush=True)
            return content
        elif etype == "reasoning":
            print(f"\033[90m{content}\033[0m", end="", flush=True)
            return ""
        elif etype == "error":
            print(f"\n\033[1;31m[错误]: {event.get('message')}\033[0m")
        return ""

    async def handle_reset(self):
        await self.client.post(f"{self.base_url}/agent/reset", params={"session_id": self.session_id})
        print("[系统]: 对话已重置")

    def print_welcome_message(self):
        print("="*50)
        print(" Firefly 语音助手 (流水线+反回声融合版) ")
        print("="*50)

async def main():
    terminal = VoiceChatTerminal()
    await terminal.run()

if __name__ == "__main__":
    asyncio.run(main())