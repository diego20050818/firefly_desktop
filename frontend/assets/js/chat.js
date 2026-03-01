// WebSocket连接实例
let ws = null;
let isConnected = false;
let sessionId = 'default';

// 当前AI消息元素和内容
let currentAiMessageElement = null;
let currentFullContent = '';
let currentToolCallElement = null;

const EMOTION_TAGS = ['墨镜','猫耳','裂开','鄙夷','生气','问号','眼泪','流汗','呆愣','开心'];
const TAG_BUFFER_MAX = 32;
let tagBuffer = '';
// 消息滚动到底部
function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

// 添加消息到聊天容器
function addMessage(text, isUser = false, showTimestamp = true) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = `message-bubble ${isUser ? 'user-message' : 'bot-message'}`;
    
    // 使用Marked解析markdown
    const markdownContent = marked.parse(text);
    div.innerHTML = `<div class="markdown-content">${markdownContent}</div>`;
    
    if (showTimestamp) {
        const timestamp = document.createElement('div');
        timestamp.className = 'timestamp mt-1 text-xs text-gray-500';
        timestamp.textContent = getCurrentTime();
        div.appendChild(timestamp);
    }
    
    container.appendChild(div);
    scrollToBottom();
}

// 添加工具调用消息（类似微信拍一拍样式）
function addToolCallMessage(toolName, argumentsStr) {
    const container = document.getElementById('messages-container');
    const toolDiv = document.createElement('div');
    toolDiv.className = 'tool-call-message text-center text-sm text-gray-500 my-2';
    toolDiv.id = `tool-${Date.now()}`; // 添加唯一ID避免冲突
    
    // 解析参数，获取关键信息用于显示
    let displayArgs = "";
    try {
        const args = JSON.parse(argumentsStr);
        // 只显示前两个参数值，避免显示过长
        const argValues = Object.values(args).slice(0, 2);
        displayArgs = argValues.length > 0 ? `(${argValues.join(', ')})` : "";
    } catch {
        displayArgs = "";
    }
    
    toolDiv.innerHTML = `
        <div class="tool-call-content flex items-center justify-center gap-2">
            <span class="tool-name font-medium text-blue-600">@${toolName}</span>
            <span class="tool-args text-gray-500">${displayArgs}</span>
            <div class="loading-spinner flex items-center gap-1">
                <div class="spinner-dot w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                <div class="spinner-dot w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0.1s;"></div>
                <div class="spinner-dot w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0.2s;"></div>
            </div>
        </div>
    `;
    
    container.appendChild(toolDiv);
    scrollToBottom();
    
    // 记录当前工具调用元素，用于后续结果关联
    currentToolCallElement = toolDiv;
}

// 更新工具调用结果
function updateToolResult(toolName, result, isSuccess = true) {
    if (currentToolCallElement) {
        const toolContent = currentToolCallElement.querySelector('.tool-call-content');
        if (toolContent) {
            const statusEmoji = isSuccess ? '✅' : '❌';
            const statusText = isSuccess ? '成功' : '失败';
            const statusColor = isSuccess ? 'text-green-600' : 'text-red-600';
            
            toolContent.innerHTML = `
                <span class="${statusColor} mr-2">${statusEmoji}</span>
                <span class="tool-name font-medium text-blue-600">@${toolName}</span>
                <span class="tool-status ${statusColor}">执行${statusText}</span>
            `;
            
            // 2秒后移除工具调用元素，让它融入到AI的回复中
            setTimeout(() => {
                if (currentToolCallElement && currentToolCallElement.parentNode) {
                    currentToolCallElement.parentNode.removeChild(currentToolCallElement);
                }
                currentToolCallElement = null;
            }, 2000);
        }
    }
}

// 添加推理消息
function addReasoningMessage(content) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'reasoning';
    
    const markdownContent = marked.parse(content);
    div.innerHTML = `
        <div class="reasoning-header flex items-center gap-2 mb-1">
            <svg class="w-4 h-4 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>
            <span class="text-sm font-medium text-blue-700">思考过程</span>
        </div>
        <div class="reasoning-content">${markdownContent}</div>
        <div class="timestamp mt-1 text-xs text-gray-500">${getCurrentTime()}</div>
    `;
    
    container.appendChild(div);
    scrollToBottom();
}

// 添加错误消息
function addErrorMessage(message) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'error-message';
    
    div.innerHTML = `
        <div class="error-header flex items-center gap-2 mb-1">
            <svg class="w-4 h-4 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
            </svg>
            <span class="text-sm font-medium text-red-700">错误</span>
        </div>
        <div class="error-content">${message}</div>
        <div class="timestamp mt-1 text-xs text-gray-500">${getCurrentTime()}</div>
    `;
    
    container.appendChild(div);
    scrollToBottom();
}

// 添加系统消息
function addSystemMessage(message) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'message-bubble bot-message';
    
    div.innerHTML = `
        <div class="system-message-content">
            <strong>🤖 系统:</strong> ${message}
        </div>
        <div class="timestamp mt-1 text-xs text-gray-500">${getCurrentTime()}</div>
    `;
    
    container.appendChild(div);
    scrollToBottom();
}

// 添加或追加AI消息内容
function appendTokenToCurrentMessage(token) {
    if (!currentAiMessageElement) {
        // 创建新的AI消息元素
        currentAiMessageElement = document.createElement('div');
        currentAiMessageElement.className = 'message-bubble bot-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'markdown-content';
        currentAiMessageElement.appendChild(contentDiv);
        
        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'timestamp mt-1 text-xs text-gray-500';
        timestampDiv.textContent = getCurrentTime();
        currentAiMessageElement.appendChild(timestampDiv);
        
        const container = document.getElementById('messages-container');
        container.appendChild(currentAiMessageElement);
    }

    currentFullContent += token;
    
    // 使用Marked解析markdown并更新内容
    const markdownContent = marked.parse(currentFullContent);
    currentAiMessageElement.querySelector('.markdown-content').innerHTML = markdownContent;
    
    scrollToBottom();
}

// 完成AI消息
function finalizeAIMessage() {
    currentAiMessageElement = null;
    currentFullContent = '';
}

// 更新连接状态
function updateStatus(status, text) {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    
    switch (status) {
        case 'connected':
            statusDot.className = 'w-2 h-2 rounded-full bg-green-500';
            statusText.textContent = '已连接';
            break;
        case 'connecting':
            statusDot.className = 'w-2 h-2 rounded-full bg-yellow-500 animate-pulse';
            statusText.textContent = '连接中...';
            break;
        case 'disconnected':
            statusDot.className = 'w-2 h-2 rounded-full bg-red-500';
            statusText.textContent = '未连接';
            break;
    }
}

// 获取当前时间
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
}

// 连接WebSocket
function connectWebSocket() {
    try {
        updateStatus('connecting', '连接中...');
        ws = new WebSocket('ws://localhost:8000/ws/agent/chat');
        
        ws.onopen = () => {
            isConnected = true;
            updateStatus('connected', '已连接');
            console.log('WebSocket connected');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };

        ws.onclose = () => {
            isConnected = false;
            updateStatus('disconnected', '已断开');
            console.log('WebSocket disconnected');
            
            // 尝试重连
            setTimeout(() => {
                connectWebSocket();
            }, 3000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateStatus('disconnected', '连接错误');
        };
    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        updateStatus('disconnected', '连接失败');
    }
}

// 处理WebSocket消息
function handleMessage(data) {
    console.log('Received message:', data);

    switch (data.type) {
        case 'token':
            appendTokenToCurrentMessage(data.content);
            break;
        case 'reasoning':
            // 在推理前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            addReasoningMessage(data.content);
            break;
        case 'tool_start':
            addToolCallMessage(data.tool_name, data.arguments);
            break;
        case 'tool_end':
            // 更新工具调用结果显示成功
            updateToolResult(data.tool_name, data.result, true);
            break;
        case 'done':
            // 工具调用完成后，开始新的AI回复气泡
            if (data.full_content) {
                addMessage(data.full_content, false, true);
            }
            finalizeAIMessage();
            enableInput();
            break;
        case 'error':
            // 在错误前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            // 如果是工具执行错误，更新工具结果显示失败
            if (currentToolCallElement) {
                updateToolResult('未知工具', data.message, false);
            } else {
                addErrorMessage(data.message);
            }
            enableInput();
            break;
        case 'system':
            // 在系统消息前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            addSystemMessage(data.message);
            break;
        case 'heartbeat':
            // 心跳消息，不做处理
            break;
        default:
            console.warn('Unknown message type:', data.type);
    }
}

// 发送聊天消息
function sendChat() {
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text) return;

    if (!isConnected) {
        addErrorMessage('WebSocket 未连接，请稍后重试');
        return;
    }

    // 添加用户消息到聊天
    addMessage(text, true);

    // 禁用发送按钮，防止重复发送
    const sendButton = document.getElementById('btn-send');
    sendButton.disabled = true;
    input.disabled = true;

    // 发送消息
    ws.send(JSON.stringify({
        type: 'user_input',
        data: { text: text },
        provider: 'deepseek'
    }));

    // 清空输入框
    input.value = '';
}

// 启用输入
function enableInput() {
    const sendButton = document.getElementById('btn-send');
    const input = document.getElementById('input');
    
    sendButton.disabled = false;
    input.disabled = false;
    input.focus();
}

// 向 C++ 宿主发送模型控制命令
function sendModelCommand(cmd) {
    try {
        window.chrome.webview.postMessage(cmd);
    } catch (e) {
        console.warn('sendModelCommand failed:', e);
    }
}

function feedTagBuffer(token) {
    tagBuffer += token;
    // 只保留末尾 TAG_BUFFER_MAX 个字符，避免无限增长
    if (tagBuffer.length > TAG_BUFFER_MAX) {
        tagBuffer = tagBuffer.slice(-TAG_BUFFER_MAX);
    }
    // 匹配 </任意内容/>
    const match = tagBuffer.match(/<\/([^\/\s]+)\/>/);
    if (match) {
        const tag = match[1];
        if (EMOTION_TAGS.includes(tag)) {
            sendModelCommand(`emotion:${tag}`);
        }
        // 命中后清空缓冲区，避免重复触发
        tagBuffer = '';
    }
}

function handleMessage(data) {
    console.log('Received message:', data);

    switch (data.type) {
        case 'token':
            // ★ 每个 token 都喂给标签检测缓冲区
            feedTagBuffer(data.content);
            appendTokenToCurrentMessage(data.content);
            break;
        case 'reasoning':
            // 在推理前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            // ★ 推理中 → 触发思考动作
            sendModelCommand('action:thinking');
            addReasoningMessage(data.content);
            break;
        case 'tool_start':
            // ★ 工具调用中 → 触发思考动作
            sendModelCommand('action:thinking');
            addToolCallMessage(data.tool_name, data.arguments);
            break;
        case 'tool_end':
            // 更新工具调用结果显示成功
            updateToolResult(data.tool_name, data.result, true);
            break;
        case 'done':
            // ★ 完成时清空标签缓冲区
            tagBuffer = '';
            // 工具调用完成后，开始新的AI回复气泡
            if (data.full_content) {
                addMessage(data.full_content, false, true);
            }
            finalizeAIMessage();
            enableInput();
            break;
        case 'error':
            tagBuffer = '';
            // 在错误前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            // 如果是工具执行错误，更新工具结果显示失败
            if (currentToolCallElement) {
                updateToolResult('未知工具', data.message, false);
            } else {
                addErrorMessage(data.message);
            }
            enableInput();
            break;
        case 'system':
            // 在系统消息前完成当前AI消息（如果有的话）
            if (currentAiMessageElement) {
                finalizeAIMessage();
            }
            addSystemMessage(data.message);
            break;
        case 'heartbeat':
            // 心跳消息，不做处理
            break;
        default:
            console.warn('Unknown message type:', data.type);
    }
}

// 页面加载完成后初始化事件监听
document.addEventListener('DOMContentLoaded', () => {
    function sendMsg(cmd) {
        window.chrome.webview.postMessage(cmd);
    }

    // 1. 拖动窗口功能 - 添加检查：如果是点击按钮，则不触发拖动
    document.getElementById('drag-handle').addEventListener('mousedown', (e) => {
        // 如果点击的是按钮，则忽略
        if (e.target.closest('button')) return;                
        
        if (e.button === 0) sendMsg('drag');
    });

    // 2. 关闭窗口功能
    document.getElementById('btn-close').addEventListener('click', (e) => {
        // 阻止事件冒泡到父级 drag-handle
        e.stopPropagation(); 
        sendMsg('close');
    });

    // 发送按钮点击事件
    document.getElementById('btn-send').addEventListener('click', sendChat);

    // 回车发送消息
    document.getElementById('input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendChat();
    });

    // 初始化滚动到底部
    scrollToBottom();
    
    // 连接WebSocket
    connectWebSocket();
});