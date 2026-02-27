import os
import sys
from loguru import logger
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
# 设置手动下载的资源文件路径
# 注意：请在导入 genie_tts 之前执行此操作
from tools.utils import load_config

config = load_config('../data/config.yaml')
tts_config = config.get('tts',None)
logger.info(tts_config)

if tts_config is None:
    logger.error(f"tts config is None")
    raise KeyError

os.environ["GENIE_DATA_DIR"] = tts_config.get('genie_path',r'.\GenieData')

import genie_tts as genie

# 第一步：加载角色语音模型
NAME = config.get('chat_bot_name','流萤')
genie.load_character(
    character_name=NAME,  # 替换为您的角色名称
    onnx_model_dir=tts_config.get('onnx_path',r'./static'),  # 包含 ONNX 模型的文件夹
    language=tts_config.get('language','zh'),  # 替换为语言代码，例如 'en', 'zh', 'jp'
)

# 第二步：设置参考音频（用于情感和语调克隆）
genie.set_reference_audio(
    character_name=NAME,  # 必须与加载的角色名称匹配
    audio_path=tts_config.get('reference_audio_path',None),  # 参考音频的路径
    audio_text=tts_config.get('reference_audio_text'),  # 对应的文本
)

# 第三步：运行 TTS 推理并生成音频
import time
begin_time = time.time()
genie.tts(
    character_name=NAME,  # 必须与加载的角色匹配
    text='南边来了他大大伯子家的大搭拉尾巴耳朵狗，北边来了他二大伯子家的二搭拉尾巴耳朵狗。他大大伯家的大搭拉尾巴耳朵狗，咬了他二大伯家的二搭拉尾巴耳朵狗一口；他二大伯家的二搭拉尾巴耳朵狗，也咬了他大大伯家的大搭拉尾巴耳朵狗一口。不知是他大大伯家的大搭拉尾巴耳朵狗，先咬了他二大伯家的二搭拉尾巴耳朵狗；还是他二大伯家的二搭拉尾巴耳朵狗，先咬了他大大伯家的大搭拉尾巴耳朵狗。',  # 要合成的文本
    play=False,  # 直接播放音频
    save_path=tts_config.get('root_path')+'test.wav',  # 输出音频文件路径
)
end_time = time.time()

# genie.wait_for_playback_done()  # 确保音频播放完成
print(f"推理时长：{end_time - begin_time}")

print("🎉 Audio generation complete!")