<div style="display: flex; justify-content: center;">
    <img src="./static/logo.png" width="280" alt="居中图片">
</div>

# Firefly 流萤

**Live2D 桌面 AI 伙伴** · Beta `v0.0.1`

[快速开始](#快速开始) · [配置说明](#配置说明) · [项目结构](#项目结构) · [开发计划](#开发计划)

---

Firefly 是一个运行在 Windows 桌面的 AI 伴侣，以崩坏：星穹铁道角色"流萤"为原型，结合 Live2D 动画、语音对话与系统工具调用，提供沉浸式的交互体验。

不同于单纯的聊天窗口，Firefly 以可见的角色形式常驻桌面，能够听你说话、回应语音、同步情绪动画，并在授权下操作你的电脑完成实际任务。

---

## 特性

**Live2D 渲染与情感同步**  
基于 Live2D Cubism SDK 5，角色动画与对话情绪实时联动，支持口型同步（LipSync）。

**语音全双工交互**  
语音输入使用 [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) 本地推理，低延迟实时识别；语音合成基于 [GeniTTS](https://github.com/High-Logic/Genie-TTS)（GPT-SoVITS 优化版），支持自定义参考音频克隆音色。

**LangChain ReAct Agent**  
对话核心由 LangChain Agent 驱动，具备多步推理与工具调用能力，当前接入 DeepSeek，多模型支持开发中。

**FastMCP 系统工具集成**  
通过 MCP 协议扩展工具集，目前支持启动应用程序、文件操作等，可通过 `mcp.json` 灵活配置与扩展。

**可配置人格**  
角色名称、语气、温度参数、TTS 音色等均通过 `config.yaml` 统一配置，无需修改代码。

---

## 系统要求

|            | 最低               | 推荐               |
| ---------- | ------------------ | ------------------ |
| **OS**     | Windows 11         | Windows 11         |
| **CPU**    | Intel i5 / Ryzen 5 | —                  |
| **RAM**    | 16 GB              | 32 GB              |
| **GPU**    | —                  | NVIDIA（TTS 加速） |
| **磁盘**   | 20 GB              | —                  |
| **Python** | 3.11+              | 3.11.4             |

> 网络连接用于 LLM API 调用；STT/TTS 均为本地推理，无需联网。

---

## 依赖准备

在启动项目前，需要手动准备以下资源：

**Live2D Cubism SDK**  
从 [Live2D 官网](https://www.live2d.com/sdk/about/) 下载 `CubismSdkForWeb-5-r.4`，解压至 `frontend/CubismSdkForWeb-5-r.4/`。Live2D SDK 使用其专有许可证，不随本项目分发。

**GeniTTS 模型**  
从 [GeniTTS](https://github.com/High-Logic/Genie-TTS) 获取预训练模型（ONNX 格式），放置于 `GenieData/` 目录，并在 `config.yaml` 中配置 `genie_path`。如需克隆特定音色，准备对应的参考音频文件（推荐 10 秒以上干净人声）。

**DeepSeek API Key**  
前往 [console.deepseek.com](https://console.deepseek.com) 注册并获取 API Key。

---

## 快速开始

```bash
# 1. 克隆项目
git clone <repository-url>
cd firefly_desktop

# 2. 配置 API Key 与路径（见下方配置说明）
# 编辑 data/config.yaml

# 3. 启动后端（推荐使用 uv）
cd backend
uv sync
uv run python main.py

# 或使用标准 pip
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py

# 4. 启动前端（编译 C++ 宿主程序后运行）
# 详见 frontend/README（待补充）

# 5. 验证
# 访问 http://localhost:8000/docs 查看 API 文档
```

---

## 配置说明
将根目录/data/config copy.yaml中的 copy字样删除，并按照指示修改配置

所有配置集中在 `data/config.yaml`：

```yaml
your_name: diego
chat_bot_name: 流萤
temperature: 0.3

stt:
  model_size: medium        # tiny / base / small / medium / large
  energy_threshold: 1000    # 麦克风触发灵敏度，环境嘈杂时适当调高

tts:
  genie_path: E:\firefly_desktop\GenieData
  reference_audio_path: E:\firefly_desktop\ref.wav   # 参考音频，影响音色
  language: zh

providers:
  deepseek:
    api_key: "sk-..."
    model: deepseek-chat
```

工具调用配置见 `data/mcp.json`，可按 MCP 协议添加自定义工具。

---

## 项目结构

```
firefly_desktop/
├── backend/
│   ├── api/app.py              # FastAPI + WebSocket
│   ├── service/
│   │   ├── agent.py            # LangChain ReAct Agent
│   │   ├── deepseek.py         # DeepSeek 接入
│   │   └── llm_service.py      # LLM 抽象基类
│   ├── tools/
│   │   ├── launch_app.py       # MCP 工具实现
│   │   ├── registry_tools.py   # 工具注册
│   │   └── stdio_mcp.py        # MCP 通信层
│   ├── voice/
│   │   ├── stt.py              # Faster Whisper 语音识别
│   │   └── tts_service.py      # GeniTTS 语音合成
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── firefly_frontend/
│   │   └── firefly_frontend.cpp  # C++ WebView2 宿主
│   ├── pages/chat/index.html     # React 主界面
│   ├── assets/
│   │   ├── model/Firefly/        # Live2D 模型文件
│   │   ├── js/
│   │   └── css/
│   └── CubismSdkForWeb-5-r.4/   # Live2D SDK（需手动放置）
│
├── data/
│   ├── config.yaml
│   └── mcp.json
├── GenieData/                    # TTS 模型（需手动放置）
├── history/                      # 对话历史
└── static/
```

---

## 交互流程

```
用户输入（文本 / 语音）
    │
    ├─ 语音 → Faster Whisper STT → 文本
    │
    ▼
LangChain ReAct Agent
    │
    ├─ 需要工具 → MCP 工具调用（启动应用、文件操作等）
    │
    ▼
LLM 生成回复
    │
    ├─ GeniTTS 合成语音
    ├─ Live2D 口型同步
    └─ 情感动画触发
```

---

## 开发计划

**进行中**
- [x] 后端架构 + FastAPI WebSocket
- [x] STT / TTS 集成
- [x] Live2D 渲染 + 口型同步
- [x] LangChain Agent + MCP 工具调用
- [ ] 对话记忆持久化
- [ ] 多模态输入（截图理解）

**规划中**
- [ ] 多 LLM 支持（Qwen、Claude 等）
- [ ] 更多系统工具（Windows API 集成、联网搜索）
- [ ] 本地 LLM 推理支持
- [ ] 知识库 / RAG（ChromaDB）

---

## 常见问题

**TTS 音色效果差**  
检查 `reference_audio_path` 指向的参考音频质量，建议使用 10 秒以左右无背景噪音的干净人声录音。

**STT 无法触发**  
调高 `energy_threshold`（如 1500~2000），并确认麦克风权限已开启。

**API 连接失败**  
确认 `config.yaml` 中的 API Key 有效，检查网络是否能访问 `api.deepseek.com`。

……

---

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/) — 后端框架
- [LangChain](https://www.langchain.com/) — Agent 编排
- [Live2D Cubism SDK](https://www.live2d.com/) — 角色渲染
- [GeniTTS](https://github.com/High-Logic/Genie-TTS) — 基于 GPT-SoVITS 的 TTS 引擎
- [whisper_real_time](https://github.com/davabase/whisper_real_time) — 实时 STT 参考实现

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE)

> Live2D SDK 及 GeniTTS 模型遵循各自许可证，不随本项目分发。

---

*我将——点燃星海。*