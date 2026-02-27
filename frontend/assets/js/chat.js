// 消息滚动到底部
function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

// 添加消息到聊天容器
function addMessage(text, isUser = false) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.classList.add('message-bubble', isUser ? 'user-message' : 'bot-message');
    div.textContent = text;
    container.appendChild(div);
    scrollToBottom();
}

// 发送聊天消息
function sendChat() {
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text) return;

    addMessage(text, true);
    input.value = '';
    input.focus();

    // 模拟回复（后续替换为真实 API）
    setTimeout(() => {
        const responses = [
            "收到你的消息了！",
            "这是一个很棒的问题！",
            "让我想想...",
            "我已经记录下你的消息了。",
            "有什么我可以帮你的吗？"
        ];
        addMessage(responses[Math.floor(Math.random() * responses.length)], false);
    }, 800);
}

// 页面加载完成后初始化事件监听
document.addEventListener('DOMContentLoaded', () => {
    function sendMsg(cmd) {
        window.chrome.webview.postMessage(cmd);
    }

    // 拖动窗口功能
    document.getElementById('drag-handle').addEventListener('mousedown', (e) => {
        if (e.button === 0) sendMsg('drag');
    });

    // 关闭窗口功能
    document.getElementById('btn-close').addEventListener('click', () => {
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
});