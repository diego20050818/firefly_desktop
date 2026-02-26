"""语音转文字（STT）模块
"""

import asyncio
import os
import numpy as np
from loguru import logger 
import speech_recognition as sr
from faster_whisper import WhisperModel
from datetime import datetime, timedelta
from queue import Queue
from time import sleep
import sys
import torch
from threading import Thread
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from tools.utils import load_config


class STTService:
    def __init__(self):
        self.config = load_config('../data/config.yaml')
        self.stt_config = self.config.get('stt', {'stt': None})

        if self.stt_config == {'stt': None}:
            logger.warning("stt配置参数为None,请检查配置文件,使用默认配置")

        self._initialize_model()
        self._setup_recorder()
        self._setup_audio_processing()
        self.listening_active = False
        self.transcription_task = None

    def _initialize_model(self):
        """初始化Faster Whisper模型"""
        model_size = self.stt_config.get('model_size', 'small')
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        self.model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type
        )
    
    def _setup_recorder(self):
        """设置录音器参数"""
        self.data_queue = Queue()
        self.recorder = sr.Recognizer()
        self.recorder.energy_threshold = self.stt_config.get('energy_threshold', 1000)
        self.recorder.dynamic_energy_threshold = self.stt_config.get('dynamic_energy_threshold', False)

        sample_rate = self.stt_config.get('Microphone_sample_rate', 16000)
        self.source = sr.Microphone(sample_rate=sample_rate)
        
    def _setup_audio_processing(self):
        """设置音频处理相关变量"""
        self.final_transcription = []
        self.current_phrase = ""
        self.phrase_timeout = self.stt_config.get('phrase_timeout', 3)
        self.phrase_time_limit = self.stt_config.get('phrase_time_limit', 2)
        
        with self.source:
            self.recorder.adjust_for_ambient_noise(self.source)

        def record_callback(_, audio: sr.AudioData):
            data = audio.get_raw_data()
            self.data_queue.put(data)

        # 开始后台监听
        self.recorder.listen_in_background(
            self.source, 
            record_callback, 
            phrase_time_limit=self.phrase_time_limit
        )
    
    def continuous_transcription_loop(self, duration=None):
        """同步方式持续监听并转录语音。"""
        logger.info(f"模型 {self.stt_config.get('model_size', 'small')} 已在 {self._get_device()} 上加载。开始录音...\n")

        phrase_time = datetime.utcnow()
        audio_buffer = b""
        start_time = datetime.utcnow()

        self.listening_active = True

        try:
            while self.listening_active:
                if duration and (datetime.utcnow() - start_time).total_seconds() >= duration:
                    break
                    
                now = datetime.utcnow()
                
                if not self.data_queue.empty():
                    if now - phrase_time > timedelta(seconds=self.phrase_timeout):
                        if self.current_phrase:
                            self.final_transcription.append(self.current_phrase)
                        audio_buffer = b""
                    
                    phrase_time = now

                    while not self.data_queue.empty():
                        audio_buffer += self.data_queue.get()

                    audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
                    segments, info = self.model.transcribe(audio_np, beam_size=1, vad_filter=True)
                    
                    self.current_phrase = ""
                    for segment in segments:
                        self.current_phrase += segment.text

                    display_text = " ".join(self.final_transcription) + " >> " + self.current_phrase
                    sys.stdout.write("\r" + display_text)
                    sys.stdout.flush()
                else:
                    sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n任务结束。")
        finally:
            self.listening_active = False

    def listen_once_vad(self) -> str:
        """智能检测说话和静默时间，捕获单次说话内容。
        
        该方法会阻塞直到检测到语音输入且随后检测到足够长的静默时间。
        """
        logger.info("VAD监听已启动，等待语音...")
        
        # 清空队列中积累的旧音频
        while not self.data_queue.empty():
            self.data_queue.get()
            
        audio_buffer = b""
        phrase_time = None
        speech_started = False
        
        # 内部参数：最大等待语音时间(秒)，防止无限期阻塞
        # 可以根据需要暴露到配置中
        MAX_WAIT = 30 
        start_wait_time = datetime.utcnow()

        while True:
            now = datetime.utcnow()
            
            if not self.data_queue.empty():
                if not speech_started:
                    logger.debug("检测到语音输入...")
                    speech_started = True
                
                phrase_time = now
                while not self.data_queue.empty():
                    audio_buffer += self.data_queue.get()
            else:
                # 如果已经开始说话，检查是否超时（静默）
                if speech_started and phrase_time:
                    silence_duration = (now - phrase_time).total_seconds()
                    if silence_duration > self.phrase_timeout:
                        logger.debug(f"静默时间已达 {silence_duration:.1f}s，停止录音。")
                        break
                
                # 如果超过最大等待时间且未开始说话，退出
                if not speech_started and (now - start_wait_time).total_seconds() > MAX_WAIT:
                    logger.warning("VAD等待语音超时。")
                    return ""
                
                sleep(0.1)

        if not audio_buffer:
            return ""

        # 转录捕获到的音频
        try:
            audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = self.model.transcribe(audio_np, beam_size=1, vad_filter=True)
            
            transcription = "".join(segment.text for segment in segments).strip()
            logger.info(f"VAD识别结果: {transcription}")
            return transcription
        except Exception as e:
            logger.error(f"VAD转录阶段异常: {e}")
            return ""

    async def start_listening(self, duration=None, mode="continuous"):
        """异步开始监听。支持 continuous (持续) 和 vad (单次触发) 模式。"""
        loop = asyncio.get_event_loop()
        if mode == "vad":
            return await loop.run_in_executor(None, self.listen_once_vad)
        else:
            await loop.run_in_executor(None, self.continuous_transcription_loop, duration)
            return self.get_transcription_result()
    
    def stop_listening(self):
        """停止监听"""
        self.listening_active = False

    def get_transcription_result(self):
        """获取完整的转录结果"""
        return " ".join(self.final_transcription) + (" " + self.current_phrase if self.current_phrase else "")
    
    def _get_device(self):
        """获取当前使用的设备"""
        return "cuda" if torch.cuda.is_available() else "cpu"


def main():
    stt_service = STTService()
    stt_service.start_listening_sync()


if __name__ == "__main__":
    main()