import os
os.environ["GENIE_DATA_DIR"] = r'E:\firefly_desktop\GenieData'
import genie_tts as genie

genie.convert_to_onnx(
    torch_pth_path=r"E:\firefly_desktop\static\firfly_tts\流萤_e15_s810.pth",  # 替换为您的 .pth 文件
    torch_ckpt_path=r"E:\firefly_desktop\static\firfly_tts\流萤-e10.ckpt",  # 替换为您的 .ckpt 文件
    output_dir=r"E:\firefly_desktop\static\firfly_tts\onnx"  # 保存 ONNX 模型的目录
)