// Settings.js - Handle Configuration UI logic

let config = {};
const API_BASE = 'http://localhost:8000';

const SECTION_MAPPING = {
    general: ['your_name', 'chat_bot_name', 'temperature', 'timeout', 'stream', 'thinking', 'history_dir', 'awake_word', 'system_prompt'],
    stt: ['stt'],
    tts: ['tts'],
    llm: ['default_provider', 'providers'],
    about: []
};

const LABEL_MAPPING = {
    your_name: '你的名字',
    chat_bot_name: '机器人名字',
    temperature: '多样性 (Temperature)',
    timeout: '超时时间 (秒)',
    stream: '流式输出',
    thinking: '显示思考过程',
    history_dir: '历史记录目录',
    awake_word: '唤醒词',
    system_prompt: '系统提示词 (System Prompt)',
    stt: '语音转文字 (STT)',
    tts: '文本转语音 (TTS)',
    providers: '服务提供商',
    default_provider: '默认模型供应商',
    // Sub-keys
    model_size: '模型大小',
    energy_threshold: '能量阈值',
    dynamic_energy_threshold: '动态能量阈值',
    Microphone_sample_rate: '采样率',
    phrase_time_limit: '录音时长限制',
    phrase_timeout: '停顿时长',
    // TTS sub-keys
    genie_path: 'Genie 数据路径',
    root_path: 'TTS 根目录',
    onnx_path: 'ONNX 模型路径',
    language: '默认语言',
    // Provider sub-keys
    api_key: 'API Key',
    base_url: 'Base URL',
    enabled: '是否启用',
    model: '模型名称'
};

// --- Host Communication ---
function sendToHost(msg) {
    try {
        if (window.chrome && window.chrome.webview) {
            window.chrome.webview.postMessage(msg);
        }
    } catch (e) {
        console.error('Failed to send message to host:', e);
    }
}

// --- Data Fetching ---
async function fetchConfig() {
    try {
        const response = await fetch(`${API_BASE}/settings/`);
        config = await response.json();
        renderSection('general');
    } catch (e) {
        console.error('Failed to fetch config:', e);
        document.getElementById('content-container').innerHTML = `<div class="text-red-500">无法连接到后端服务: ${e.message}</div>`;
    }
}

async function updateSetting(keyPath, value) {
    try {
        // Convert value type if necessary
        let finalValue = value;
        if (value === 'true') finalValue = true;
        if (value === 'false') finalValue = false;
        if (!isNaN(value) && typeof value === 'string' && value.trim() !== '') {
            finalValue = value.includes('.') ? parseFloat(value) : parseInt(value);
        }

        const response = await fetch(`${API_BASE}/settings/modify_setting`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                key: keyPath,
                new_value: finalValue
            })
        });

        if (response.ok) {
            console.log(`Updated ${keyPath} to`, finalValue);
            // Optionally show a toast
        } else {
            console.error('Failed to update setting');
        }
    } catch (e) {
        console.error('Update setting error:', e);
    }
}

// --- Rendering Logic ---
function renderSection(sectionId) {
    const container = document.getElementById('content-container');
    container.innerHTML = '';

    if (sectionId === 'about') {
        container.innerHTML = `
            <div class="card text-center py-12">
                <div class="flex justify-center mb-4">
                    <a href="https://ibb.co/LDzK8zmz"><img src="https://i.ibb.co/LDzK8zmz/icon.png" alt="icon" border="0"></a>
                </div>
                <h2 class="text-2xl font-bold text-gray-800">Firefly AI Desktop</h2>
                <p class="text-gray-500 mt-2">Version 0.0.1-beta</p>
                <div class="mt-8 space-y-4">
                    <p class="text-sm text-gray-600">极简、高效、美丽的 AI 桌宠助手</p>
                    <div class="flex justify-center gap-4 mt-8">
                        <a href="https://github.com/diego20050818/firefly_desktop" class="px-6 py-2 bg-gray-100 rounded-full text-sm font-semibold hover:bg-gray-200">GitHub</a>
                        <a href="#" class="px-6 py-2 bg-[#61c0bf] text-white rounded-full text-sm font-semibold hover:opacity-90">检查更新</a>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const keys = SECTION_MAPPING[sectionId] || [];

    // Header
    const sectionTitle = document.querySelector(`.sidebar-item[data-section="${sectionId}"]`).innerText;
    const header = document.createElement('h2');
    header.className = 'section-title';
    header.innerHTML = sectionTitle;
    container.appendChild(header);

    keys.forEach(key => {
        const val = config[key];
        if (val !== undefined) {
            if (typeof val === 'object' && !Array.isArray(val) && key !== 'system_prompt') {
                // Nested object (STT, TTS, Providers)
                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `<h3 class="font-bold text-gray-700 mb-4 border-b pb-2">${LABEL_MAPPING[key] || key}</h3>`;

                Object.entries(val).forEach(([subKey, subVal]) => {
                    const subKeyPath = `${key}.${subKey}`;
                    if (typeof subVal === 'object' && subVal !== null) {
                        // Deeply nested (like providers.deepseek)
                        const subGroup = document.createElement('div');
                        subGroup.className = 'mt-4 pt-4 border-t';
                        subGroup.innerHTML = `<h4 class="text-sm font-bold text-gray-500 mb-3">${subKey.toUpperCase()}</h4>`;
                        Object.entries(subVal).forEach(([deepKey, deepVal]) => {
                            subGroup.appendChild(createField(`${subKeyPath}.${deepKey}`, deepVal));
                        });
                        card.appendChild(subGroup);
                    } else {
                        card.appendChild(createField(subKeyPath, subVal));
                    }
                });
                container.appendChild(card);
            } else {
                // Flat field
                container.appendChild(createField(key, val));
            }
        }
    });
}

function createField(keyPath, value) {
    const div = document.createElement('div');
    div.className = 'form-group';

    const labelStr = keyPath.split('.').pop();
    const displayName = LABEL_MAPPING[labelStr] || labelStr;

    const label = document.createElement('label');
    label.className = 'form-label';
    label.innerText = displayName;
    div.appendChild(label);

    if (keyPath.endsWith('system_prompt')) {
        const textarea = document.createElement('textarea');
        textarea.className = 'form-input min-h-[150px]';
        textarea.value = value;
        textarea.onchange = (e) => updateSetting(keyPath, e.target.value);
        div.appendChild(textarea);
    } else if (typeof value === 'boolean') {
        const switchLabel = document.createElement('label');
        switchLabel.className = 'form-switch';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = value;
        input.onchange = (e) => updateSetting(keyPath, e.target.checked);
        const slider = document.createElement('span');
        slider.className = 'slider';
        switchLabel.appendChild(input);
        switchLabel.appendChild(slider);
        div.appendChild(switchLabel);
    } else {
        const input = document.createElement('input');
        input.className = 'form-input';
        input.value = value;
        input.onchange = (e) => updateSetting(keyPath, e.target.value);
        div.appendChild(input);
    }

    return div;
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // Window controls
    document.getElementById('drag-handle').addEventListener('mousedown', () => sendToHost('drag'));
    document.getElementById('btn-close').addEventListener('click', () => sendToHost('close'));

    // Sidebar navigation
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            renderSection(item.dataset.section);
        });
    });

    fetchConfig();
});
