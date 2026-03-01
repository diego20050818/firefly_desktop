// WebSocket连接实例
let ws = null;
let isConnected = false;
let sessionId = 'default';

// 当前AI消息元素和内容
let currentAiMessageElement = null;
let currentFullContent = '';
let currentToolCallElement = null;
let isStreaming = false; // 用于追踪是否正在流式输出，解决重复气泡问题

const EMOTION_TAGS = ['墨镜', '猫耳', '裂开', '鄙夷', '生气', '问号', '眼泪', '流汗', '呆愣', '开心'];
const TAG_BUFFER_MAX = 32;
let tagBuffer = '';

// TTS 状态
let ttsEnabled = false;

// STT 状态
let spacePressed = false;
let spacePressTimer = null;
let isListening = false;

// 消息滚动到底部
function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
    });
}

// 过滤标签函数
function filterTags(text) {
    if (!text) return "";
    // 移除 </ 任意内容 /> 这种表情标签
    return text.replace(/<\/([^>]+)\/>/g, "");
}

// 添加消息到聊天容器
function addMessage(text, isUser = false, showTimestamp = true) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = `message-bubble ${isUser ? 'user-message shadow-sm' : 'bot-message shadow-sm'}`;

    // 过滤标签后再解析markdown
    const filteredText = filterTags(text);
    const markdownContent = marked.parse(filteredText);
    div.innerHTML = `<div class="markdown-content">${markdownContent}</div>`;

    if (showTimestamp) {
        const timestamp = document.createElement('div');
        timestamp.className = 'timestamp text-right px-1';
        timestamp.textContent = getCurrentTime();
        div.appendChild(timestamp);
    }

    container.appendChild(div);
    scrollToBottom();

    // 如果是AI消息且开启了TTS，则请求发音（过滤标签）
    if (!isUser && ttsEnabled && filteredText) {
        generateTTS(filteredText.replace(/<\/?[^>]+(>|$)/g, ""));
    }
}

// 添加工具调用消息
function addToolCallMessage(toolName, argumentsStr) {
    const container = document.getElementById('messages-container');
    const toolDiv = document.createElement('div');
    toolDiv.className = 'tool-call-message';

    toolDiv.innerHTML = `<div class="tool-call-content animate-pulse">⚙️ 正在调用 ${toolName}...</div>`;

    container.appendChild(toolDiv);
    scrollToBottom();
    currentToolCallElement = toolDiv;
}

// 更新工具调用结果
function updateToolResult(toolName, result, isSuccess = true) {
    if (currentToolCallElement) {
        const content = currentToolCallElement.querySelector('.tool-call-content');
        if (content) {
            content.classList.remove('animate-pulse');
            content.innerHTML = isSuccess ? `✅ 已执行 ${toolName}` : `❌ ${toolName} 执行失败`;

            setTimeout(() => {
                if (currentToolCallElement) {
                    currentToolCallElement.style.opacity = '0';
                    setTimeout(() => {
                        currentToolCallElement?.remove();
                        currentToolCallElement = null;
                    }, 300);
                }
            }, 2000);
        }
    }
}

// 添加推理消息 - 使用折叠组件
let currentReasoningContent = '';
function addReasoningMessage(content) {
    const container = document.getElementById('messages-container');

    // 检查是否已经存在最新的思考气泡，如果是流式推送则追加
    let details = container.querySelector('.reasoning-details:last-child');
    if (!details || details.dataset.finalized === 'true') {
        details = document.createElement('details');
        details.className = 'reasoning-details';
        details.open = true; // 默认展开正在进行的思考
        details.innerHTML = `
            <summary class="reasoning-summary">思考中...</summary>
            <div class="reasoning-content"></div>
        `;
        container.appendChild(details);
        currentReasoningContent = ''; // 重置积累的内容
    }

    const contentDiv = details.querySelector('.reasoning-content');
    currentReasoningContent += content;
    // 使用 marked 渲染累计的内容
    contentDiv.innerHTML = marked.parse(currentReasoningContent);
    scrollToBottom();
}

function finalizeReasoning() {
    const container = document.getElementById('messages-container');
    const details = container.querySelector('.reasoning-details:last-child');
    if (details) {
        details.querySelector('.reasoning-summary').textContent = '已思考';
        details.dataset.finalized = 'true';
    }
}

// 添加错误消息
function addErrorMessage(message) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'error-message';
    div.innerHTML = `⚠️ ${message}`;
    container.appendChild(div);
    scrollToBottom();
}

// 添加系统消息
function addSystemMessage(message) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'text-center text-[10px] text-gray-400 my-2 uppercase tracking-widest';
    div.textContent = `— ${message} —`;
    container.appendChild(div);
    scrollToBottom();
}

// 添加或追加AI消息内容
function appendTokenToCurrentMessage(token) {
    isStreaming = true; // 标记正在流式传输
    if (!currentAiMessageElement) {
        currentAiMessageElement = document.createElement('div');
        currentAiMessageElement.className = 'message-bubble bot-message shadow-sm';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'markdown-content';
        currentAiMessageElement.appendChild(contentDiv);

        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'timestamp text-right px-1';
        timestampDiv.textContent = getCurrentTime();
        currentAiMessageElement.appendChild(timestampDiv);

        document.getElementById('messages-container').appendChild(currentAiMessageElement);
    }

    currentFullContent += token;
    // 流式渲染时也保持过滤标签
    const filteredDisplay = filterTags(currentFullContent);
    currentAiMessageElement.querySelector('.markdown-content').innerHTML = marked.parse(filteredDisplay);
    scrollToBottom();
}

// 完成AI消息
function finalizeAIMessage() {
    if (ttsEnabled && currentFullContent) {
        // 最终合成时务必过滤标签
        const cleanText = filterTags(currentFullContent).replace(/<\/?[^>]+(>|$)/g, "");
        if (cleanText.trim()) {
            generateTTS(cleanText);
        }
    }
    currentAiMessageElement = null;
    currentFullContent = '';
    isStreaming = false;
}

// 更新连接状态
function updateStatus(status) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    if (status === 'connected') {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_4px_#4ade80]';
        text.textContent = '已在线';
    } else if (status === 'connecting') {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse';
        text.textContent = '连接中';
    } else {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-red-400';
        text.textContent = '离线';
    }
}

function getCurrentTime() {
    return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

// API 调用
async function generateTTS(text) {
    if (!text || !text.trim()) return;
    try {
        await fetch('http://localhost:8000/tts/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                character_name: "流萤"
            })
        });
    } catch (e) {
        console.error('TTS failed:', e);
    }
}

let sttToggle = false;
async function toggleSTT() {
    if (sttToggle) {
        sttToggle = false;
        stopSTT();
    } else {
        sttToggle = true;
        startSTT();
    }
}

async function startSTT() {
    isListening = true;
    document.getElementById('siri-wave').classList.add('active');
    document.getElementById('input').placeholder = "正在倾听...";
    sendModelCommand('action:listening');
    try {
        await fetch('http://localhost:8000/stt/start', { method: 'POST' });
        checkSTTResult();
    } catch (e) {
        console.error('STT Start failed:', e);
    }
}

async function checkSTTResult() {
    if (!isListening) return;
    try {
        const resp = await fetch('http://localhost:8000/stt/stop', { method: 'POST' });
        const data = await resp.json();
        if (data.transcription) {
            isListening = false;
            sttToggle = false;
            document.getElementById('siri-wave').classList.remove('active');
            document.getElementById('input').placeholder = "输入消息或 Ctrl+Space 语音输入...";
            document.getElementById('input').value = data.transcription;
            sendChat();
        } else if (isListening) {
            setTimeout(checkSTTResult, 1000);
        }
    } catch (e) {
        console.error('Check STT result failed:', e);
    }
}

async function stopSTT() {
    isListening = false;
    document.getElementById('siri-wave').classList.remove('active');
    document.getElementById('input').placeholder = "输入消息或 Ctrl+Space 语音输入...";
}

// WebSocket
function connectWebSocket() {
    updateStatus('connecting');
    ws = new WebSocket('ws://localhost:8000/ws/agent/chat');

    ws.onopen = () => {
        isConnected = true;
        updateStatus('connected');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWSMessage(data);
    };

    ws.onclose = () => {
        isConnected = false;
        updateStatus('disconnected');
        setTimeout(connectWebSocket, 3000);
    };
}

function handleWSMessage(data) {
    switch (data.type) {
        case 'token':
            feedTagBuffer(data.content);
            appendTokenToCurrentMessage(data.content);
            // 模型说话同步
            if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage("speaking");
            } else if (typeof speak === 'function') {
                speak(500);
            }
            break;
        case 'reasoning':
            addReasoningMessage(data.content);
            sendModelCommand('action:thinking');
            break;
        case 'tool_start':
            addToolCallMessage(data.tool_name, data.arguments);
            sendModelCommand('action:thinking');
            break;
        case 'tool_end':
            updateToolResult(data.tool_name, data.result, true);
            break;
        case 'done':
            finalizeReasoning();
            // ★ 修复重复气泡的核心逻辑：如果正在流式输出，则不再通过 addMessage 创建新气泡
            // data.full_content 只在非流式或需要同步完整记录时有用
            if (!isStreaming && data.full_content) {
                addMessage(data.full_content, false, true);
            }
            finalizeAIMessage();
            enableInput();
            break;
        case 'error':
            finalizeReasoning();
            finalizeAIMessage();
            // ★ 修改工具执行错误接收逻辑
            if (currentToolCallElement) {
                updateToolResult('工具', data.message, false);
            } else {
                addErrorMessage(data.message || '未知错误');
            }
            enableInput();
            break;
        case 'system':
            addSystemMessage(data.message);
            break;
    }
}

function sendChat() {
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text || !isConnected) return;

    addMessage(text, true);
    input.value = '';
    input.disabled = true;

    ws.send(JSON.stringify({
        type: 'user_input',
        data: { text: text },
        provider: 'deepseek'
    }));
}

function enableInput() {
    const input = document.getElementById('input');
    input.disabled = false;
    input.focus();
}

function sendModelCommand(cmd) {
    try { window.chrome.webview.postMessage(cmd); } catch (e) { }
}

function feedTagBuffer(token) {
    tagBuffer += token;
    if (tagBuffer.length > TAG_BUFFER_MAX) tagBuffer = tagBuffer.slice(-TAG_BUFFER_MAX);
    const match = tagBuffer.match(/<\/([^\/\s]+)\/>/);
    if (match) {
        if (EMOTION_TAGS.includes(match[1])) sendModelCommand(`emotion:${match[1]}`);
        tagBuffer = '';
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 基础交互
    document.getElementById('drag-handle').addEventListener('mousedown', (e) => {
        if (!e.target.closest('button')) sendModelCommand('drag');
    });

    document.getElementById('btn-close').addEventListener('click', () => sendModelCommand('close'));
    document.getElementById('btn-send').addEventListener('click', sendChat);
    document.getElementById('input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendChat();
    });

    // TTS 开关
    document.getElementById('btn-tts').addEventListener('click', () => {
        ttsEnabled = !ttsEnabled;
        const btn = document.getElementById('btn-tts');
        const dot = document.getElementById('tts-status-dot');
        const text = document.getElementById('tts-status-text');

        btn.innerHTML = ttsEnabled ? '🔊' : '🔇';
        dot.className = ttsEnabled ? 'w-1.5 h-1.5 rounded-full bg-green-400' : 'w-1.5 h-1.5 rounded-full bg-gray-400';
        text.textContent = ttsEnabled ? 'TTS ON' : 'TTS OFF';
    });

    // 侧边栏控制
    const panel = document.getElementById('settings-panel');
    const overlay = document.getElementById('menu-overlay');

    document.getElementById('open-settings').addEventListener('click', () => {
        panel.classList.add('open');
        overlay.classList.add('active');
    });

    const closeMenu = () => {
        panel.classList.remove('open');
        overlay.classList.remove('active');
    };

    document.getElementById('close-settings').addEventListener('click', closeMenu);
    overlay.addEventListener('click', closeMenu);

    // 新对话
    document.getElementById('btn-new-chat').addEventListener('click', async () => {
        try {
            await fetch(`http://localhost:8000/agent/reset?session_id=${sessionId}`, { method: 'POST' });
            document.getElementById('messages-container').innerHTML = '';
            addSystemMessage('对话已重置');
            closeMenu();
        } catch (e) {
            console.error('Reset failed:', e);
        }
    });

    // ★ STT 逻辑修改：从空格改为 Ctrl+Space
    document.addEventListener('keydown', (e) => {
        const isInput = document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA';
        if (e.code === 'Space' && (e.ctrlKey || e.metaKey) && !isInput) {
            e.preventDefault();
            if (!e.repeat) {
                toggleSTT();
            }
        }
    });

    // 物理按钮触发语音
    document.getElementById('btn-voice').addEventListener('click', toggleSTT);

    // 启用 TTS 后端提示
    fetch('http://localhost:8000/tts/enable', { method: 'POST' }).catch(console.error);

    connectWebSocket();
});
