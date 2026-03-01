# backend/voice/tts_service.py
import time
import requests
import pyaudio
import threading
import asyncio
import os
import sys
from loguru import logger
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from tools.utils import load_config

config = load_config('../data/config.yaml')
tts_config = config.get('tts', None)

if tts_config is None:
    logger.error(f"tts config is None")
    raise KeyError

os.environ["GENIE_DATA_DIR"] = tts_config.get('genie_path', r'.\GenieData')
import genie_tts as genie

# --- Configuration ---
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8002
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

BYTES_PER_SAMPLE = 2
CHANNELS = 1
SAMPLE_RATE = 32000

class AsyncTTSService:
    def __init__(self):
        self.server_thread = None
        self.character_loaded = False
        self.name = config.get('chat_bot_name', '流萤')
        self.server_running = False
        self.is_speaking = False
        self.tts_enabled = False

    # 状态管理
    async def enable_tts(self):
        """启用TTS功能"""
        if not self._ensure_server():
            return False
        
        self.tts_enabled = True
        logger.info("TTS enabled")
        return True

    async def disable_tts(self):
        """禁用TTS功能"""
        self.tts_enabled = False
        # 如果正在播放则停止
        if self.is_speaking:
            await self.stop_all_tasks()
        logger.info("TTS disabled")
        return True

    def get_tts_status(self):
        """获取TTS状态"""
        return {
            "enabled": self.tts_enabled,
            "speaking": self.is_speaking,
            "server_running": self.server_running,
            "character_loaded": self.character_loaded
        }


    # ------------------------------------------------------------------ #
    #  核心修复：探测已有服务，不依赖进程内 server_running 标志            #
    # ------------------------------------------------------------------ #
    def _ping_server(self, timeout: float = 5.0) -> bool:
        """
        同步版健康检查。
        genie 没有 /health 端点，会返回 404，但只要能收到任意 HTTP 响应
        就说明服务器已在线。只有连接被拒（ConnectionError/Timeout）才是真正未启动。
        """
        try:
            requests.get(f"{BASE_URL}/health", timeout=timeout)
            return True   # 200、404、405… 都算在线
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return False
        except Exception:
            return False

    async def _async_ping_server(self, timeout: float = 5.0) -> bool:
        """异步版健康检查"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._ping_server(timeout))

    def connect_to_existing_server(self) -> bool:
        """
        当 TTS server 已由其他进程（如 main.py）启动时，
        调用此方法让当前实例感知到服务器存在，而不是重新 start_server()。

        用法（test_chat.py 顶部）：
            from voice.tts_service import tts_service
            tts_service.connect_to_existing_server()   # ← 加这一行
        """
        if self._ping_server():
            self.server_running = True
            logger.success(f"Connected to existing TTS server at {BASE_URL}")
            return True
        else:
            logger.error(
                f"Cannot connect to TTS server at {BASE_URL}. "
                "Make sure main.py has been started first."
            )
            return False

    def _ensure_server(self) -> bool:
        """
        所有对外方法的统一入口检查。
        server_running 为 True 时仍做一次轻量 ping，防止服务崩溃后假阳性。
        """
        if not self.server_running:
            logger.error("TTS Server is not running (server_running=False). "
                         "Call start_server() or connect_to_existing_server() first.")
            return False
        # 可选：取消下一行注释以在每次调用时都做 ping（性能换可靠性）
        # if not self._ping_server(timeout=3):
        #     logger.error("TTS Server health check failed (server not responding).")
        #     return False
        return True

    # ------------------------------------------------------------------ #
    #  原有方法（检查改用 _ensure_server）                                #
    # ------------------------------------------------------------------ #
    def start_server(self):
        """启动 TTS 服务器（在同进程内启动 genie）"""
        def run_server():
            genie.start_server(host=SERVER_HOST, port=SERVER_PORT, workers=1)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        # 等待服务器就绪，用轮询代替固定 sleep，更可靠
        for i in range(20):
            time.sleep(1)
            if self._ping_server():
                self.server_running = True
                logger.success(f"TTS Server started successfully on {BASE_URL} (after {i+1}s)")
                return
        logger.error("TTS Server did not become ready within 20 seconds")

    def stop_server(self):
        self.server_running = False
        logger.info("TTS Server marked as stopped")

    async def check_server_status(self) -> bool:
        return await self._async_ping_server()

    async def load_character(self, character_name=None, onnx_model_dir=None, language=None):
        if not self._ensure_server():
            return False
        if character_name is None:
            character_name = self.name
        if onnx_model_dir is None:
            onnx_model_dir = tts_config.get('onnx_path', r'E:\firefly_desktop\static\firfly_tts\pro\onnx')
        if language is None:
            language = tts_config.get('language', 'zh')

        load_payload = {
            "character_name": character_name,
            "onnx_model_dir": onnx_model_dir,
            "language": language
        }
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: requests.post(f"{BASE_URL}/load_character", json=load_payload, timeout=30))
            response.raise_for_status()
            logger.success(f"Character {character_name} loaded: {response.json()['message']}")
            self.character_loaded = True
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to load character: {e}")
            return False

    async def set_reference_audio(self, character_name=None, audio_path=None, audio_text=None, language=None):
        if not self._ensure_server():
            return False
        if character_name is None:
            character_name = self.name
        if audio_path is None:
            audio_path = tts_config.get('reference_audio_path', None)
        if audio_text is None:
            audio_text = tts_config.get('reference_audio_text')
        if language is None:
            language = tts_config.get('language', 'zh')

        ref_audio_payload = {
            "character_name": character_name,
            "audio_path": audio_path,
            "audio_text": audio_text,
            "language": language
        }
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: requests.post(f"{BASE_URL}/set_reference_audio", json=ref_audio_payload, timeout=30))
            response.raise_for_status()
            logger.success(f"Reference audio set: {response.json()['message']}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set reference audio: {e}")
            return False

    async def generate_speech(self, text, character_name=None, split_sentence=True, save_path=None):
        if not self._ensure_server() or not self.tts_enabled:
            return False
            
        if character_name is None:
            character_name = self.name

        self.is_speaking = True  # 设置正在说话状态
        tts_payload = {
            "character_name": character_name,
            "text": text,
            "split_sentence": split_sentence
        }
        if save_path:
            tts_payload["save_path"] = save_path

        p = pyaudio.PyAudio()

        def make_request_and_stream():
            stream_obj = None
            try:
                with requests.post(f"{BASE_URL}/tts", json=tts_payload, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    logger.info("Connected to audio stream, starting playback...")
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            if stream_obj is None:
                                stream_obj = p.open(
                                    format=p.get_format_from_width(BYTES_PER_SAMPLE),
                                    channels=CHANNELS,
                                    rate=SAMPLE_RATE,
                                    output=True
                                )
                            stream_obj.write(chunk)
                    logger.info("Audio stream finished.")
                    return True
            except Exception as e:
                logger.error(f"Error during playback: {e}")
                return False
            finally:
                if stream_obj:
                    stream_obj.stop_stream()
                    stream_obj.close()
                p.terminate()
                self.is_speaking = False  # 播放结束后设置为非说话状态

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, make_request_and_stream)

    async def fetch_audio_bytes(self, text, character_name=None, split_sentence=True) -> bytes | None:
        """
        只合成、不播放，返回完整 PCM 字节。
        可在上一句播放时并发调用，实现流水线预合成。
        """
        if not self._ensure_server():
            return None
        if character_name is None:
            character_name = self.name

        tts_payload = {
            "character_name": character_name,
            "text": text,
            "split_sentence": split_sentence
        }

        def fetch():
            try:
                with requests.post(f"{BASE_URL}/tts", json=tts_payload, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    return b"".join(response.iter_content(chunk_size=4096))
            except Exception as e:
                logger.error(f"fetch_audio_bytes failed: {e}")
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fetch)

    @staticmethod
    def play_audio_bytes(audio: bytes):
        """同步播放 PCM 字节（在 executor 里调用）"""
        if not audio:
            return
        p = pyaudio.PyAudio()
        stream_obj = None
        try:
            stream_obj = p.open(
                format=p.get_format_from_width(BYTES_PER_SAMPLE),
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True
            )
            # 分块写入，避免一次性写入过大造成卡顿
            chunk = 1024
            for i in range(0, len(audio), chunk):
                stream_obj.write(audio[i:i + chunk])
        except Exception as e:
            logger.error(f"play_audio_bytes failed: {e}")
        finally:
            if stream_obj:
                stream_obj.stop_stream()
                stream_obj.close()
            p.terminate()

    async def stream_generate_speech(self, text, character_name=None, split_sentence=True, save_path=None):
        """流式生成语音 - 逐块播放"""
        if not self._ensure_server() or not self.tts_enabled:
            return False
        if character_name is None:
            character_name = self.name

        self.is_speaking = True  # 设置正在说话状态
        tts_payload = {
            "character_name": character_name,
            "text": text,
            "split_sentence": split_sentence
        }
        if save_path:
            tts_payload["save_path"] = save_path

        p = pyaudio.PyAudio()

        def make_request_and_stream():
            stream_obj = None
            try:
                with requests.post(f"{BASE_URL}/tts", json=tts_payload, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    logger.info("Connected to audio stream, starting streaming playback...")
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            if stream_obj is None:
                                stream_obj = p.open(
                                    format=p.get_format_from_width(BYTES_PER_SAMPLE),
                                    channels=CHANNELS,
                                    rate=SAMPLE_RATE,
                                    output=True
                                )
                            stream_obj.write(chunk)
                    logger.info("Streaming playback finished.")
                    return True
            except Exception as e:
                logger.error(f"Error during streaming playback: {e}")
                return False
            finally:
                if stream_obj:
                    stream_obj.stop_stream()
                    stream_obj.close()
                p.terminate()
                self.is_speaking = False  # 播放结束后设置为非说话状态

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, make_request_and_stream)

    async def initialize_character(self):
        """加载模型 + 设置参考音频"""
        success = await self.load_character()
        if success:
            success = await self.set_reference_audio()
        return success

    async def unload_character(self, character_name=None):
        if not self._ensure_server():
            return False
        if character_name is None:
            character_name = self.name
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: requests.post(f"{BASE_URL}/unload_character",
                                            json={"character_name": character_name}, timeout=10))
            response.raise_for_status()
            logger.success(f"Character {character_name} unloaded")
            self.character_loaded = False
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to unload character: {e}")
            return False

    async def clear_reference_audio_cache(self):
        if not self._ensure_server():
            return False
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: requests.post(f"{BASE_URL}/clear_reference_audio_cache", timeout=10))
            response.raise_for_status()
            logger.success("Reference audio cache cleared")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to clear reference audio cache: {e}")
            return False

    async def stop_all_tasks(self):
        if not self._ensure_server():
            return False
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: requests.post(f"{BASE_URL}/stop", timeout=10))
            response.raise_for_status()
            logger.info("All TTS tasks stopped")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stop TTS tasks: {e}")
            return False


# 全局实例
tts_service = AsyncTTSService()


# ====================================================================== #
#  独立测试入口                                                           #
#  用法：确保 main.py 已在另一个终端运行，然后：                          #
#       cd backend && python -m voice.tts_service                        #
# ====================================================================== #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TTS Service standalone test")
    parser.add_argument("--text", type=str, default="你好，我是流萤，很高兴认识你。",
                        help="要合成的测试文本")
    parser.add_argument("--start-server", action="store_true",
                        help="在当前进程启动 genie 服务器（main.py 未运行时使用）")
    parser.add_argument("--stream", action="store_true",
                        help="使用流式播放（默认非流式）")
    args = parser.parse_args()

    async def run_test():
        svc = AsyncTTSService()

        # ① 连接或启动服务器
        if args.start_server:
            logger.info("Starting TTS server in this process...")
            svc.start_server()          # 内部已用轮询等待就绪
        else:
            logger.info("Trying to connect to existing TTS server (started by main.py)...")
            if not svc.connect_to_existing_server():
                logger.error("No TTS server found. Run main.py first, or pass --start-server.")
                return

        # ② 加载角色 + 参考音频
        logger.info("Initializing character...")
        ok = await svc.initialize_character()
        if not ok:
            logger.error("Character initialization failed. Aborting.")
            return

        # ③ 合成语音
        test_text = args.text
        logger.info(f"Synthesizing: {test_text!r}")

        if args.stream:
            success = await svc.stream_generate_speech(test_text)
        else:
            success = await svc.generate_speech(test_text)

        if success:
            logger.success("✅ TTS playback completed successfully")
        else:
            logger.error("❌ TTS playback failed")

        # ④ 可选：卸载角色
        # await svc.unload_character()

    asyncio.run(run_test())