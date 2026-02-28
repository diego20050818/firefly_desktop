/**
 * E:\firefly_desktop\frontend\assets\js\model.js
 */

window.PIXI = PIXI;
let live2dModel; 
let expressionTimer = null; // 用于管理表情回正的定时器

window.onload = async () => {
    if (!window.Live2DCubismCore) return;
    const L2D = PIXI.live2d ? PIXI.live2d.Live2DModel : null;
    if (L2D) {
        try {
            if (typeof L2D.registerCubismCore === 'function') {
                L2D.registerCubismCore(window.Live2DCubismCore);
            }
            await initLive2D();
        } catch (e) { console.error(e); }
    }
};

async function initLive2D() {
    const canvas = document.getElementById('live2d-canvas');
    const app = new PIXI.Application({
        view: canvas,
        autoStart: true,
        backgroundAlpha: 0,
        antialias: true,
        resizeTo: window
    });

    const modelPath = '/assets/model/Firefly/Firefly.model3.json';

    try {
        live2dModel = await PIXI.live2d.Live2DModel.from(modelPath);
        app.stage.addChild(live2dModel);

        // 居中适配
        live2dModel.anchor.set(0.5, 0.5);
        const fitModel = () => {
            const baseScale = (window.innerHeight * 0.8) / live2dModel.height;
            live2dModel.scale.set(baseScale);
            live2dModel.x = window.innerWidth / 2;
            live2dModel.y = window.innerHeight / 2;
        };
        fitModel();
        window.onresize = fitModel;

        // 鼠标跟随
        live2dModel.interactive = true;
        app.ticker.add(() => {
            const target = app.renderer.events.pointer.global;
            live2dModel.focus(target.x, target.y);
        });

        // --- 1. 拖放支持 ---
        window.addEventListener('dragover', (e) => {
            e.preventDefault(); // 必须阻止默认行为才能触发 drop
            e.dataTransfer.dropEffect = 'copy';
        });

        window.addEventListener('drop', (e) => {
            e.preventDefault();
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                console.log("检测到拖入文件:", files[0].name);
                // 这里可以扩展功能：比如判断是图片就更换背景，或者让流萤说话
                speak(2000); 
            }
        });

        // 窗口拖动 (点击非交互区)
        canvas.addEventListener('mousedown', (e) => {
            if (e.button === 0) window.chrome.webview.postMessage("drag");
        });

        // Ctrl + 滚轮缩放
        window.addEventListener('wheel', (e) => {
            if (e.ctrlKey) {
                e.preventDefault();
                const factor = e.deltaY > 0 ? 0.9 : 1.1;
                live2dModel.scale.set(live2dModel.scale.x * factor);
            }
        }, { passive: false });

        createDebugButtons();

    } catch (e) { console.error("加载失败:", e); }
}

/**
 * 带有“自动回正”逻辑的表情切换
 */
function setExpressionWithTimer(name) {
    if (!live2dModel) return;

    console.log("切换表情:", name);
    live2dModel.expression(name);

    // 清除之前的定时器
    if (expressionTimer) clearTimeout(expressionTimer);

    // 5秒后重置表情
    expressionTimer = setTimeout(() => {
        console.log("表情回正至默认");
        live2dModel.expression(""); // 传空字符串通常重置为默认脸
    }, 5000);
}

/**
 * 带有“自动回正”逻辑的动作播放
 */
function playMotionWithTimer(group, index) {
    if (!live2dModel) return;

    live2dModel.motion(group, index);

    // 5秒后强制回到 idle（即使动作没播完或播完了处于静止）
    setTimeout(() => {
        console.log("动作回正至 Idle");
        live2dModel.motion('idle', 0);
    }, 5000);
}

/**
 * 自然说话逻辑
 */
let isSpeaking = false;
function speak(duration = 2000) {
    if (!live2dModel || isSpeaking) return;
    isSpeaking = true;
    let startTime = performance.now();
    let targetMouth = 0;
    let currentMouth = 0;

    const update = () => {
        const now = performance.now();
        const elapsed = now - startTime;
        if (elapsed < duration) {
            if (Math.random() > 0.8) targetMouth = Math.random() * 0.8;
            currentMouth += (targetMouth - currentMouth) * 0.2;
            live2dModel.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', currentMouth);
            requestAnimationFrame(update);
        } else {
            live2dModel.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', 0);
            isSpeaking = false;
        }
    };
    update();
}

function createDebugButtons() {
    const btnContainer = document.createElement('div');
    btnContainer.style.cssText = `
        position: absolute; top: 10px; left: 10px; z-index: 1000;
        background: rgba(0, 0, 0, 0.6); padding: 10px; color: white;
        border-radius: 8px; font-family: "Microsoft YaHei", sans-serif; 
        max-height: 85vh; overflow-y: auto; pointer-events: auto;
    `;
    document.body.appendChild(btnContainer);

    // 按钮逻辑：调用带 Timer 的函数
    const speakBtn = document.createElement('button');
    speakBtn.textContent = "🔊 触发说话";
    speakBtn.style.cssText = 'display:block; width:100%; margin-bottom:12px; padding:8px; background:#4CAF50; color:white; border:none; cursor:pointer; border-radius:4px;';
    speakBtn.onclick = () => speak(3000);
    btnContainer.appendChild(speakBtn);

    const specialMotions = [
        { name: "变身", index: 0 }, { name: "捂手", index: 1 },
        { name: "拍手", index: 2 }, { name: "思考", index: 3 },
        { name: "抱胸", index: 4 }, { name: "叉腰", index: 5 },
        { name: "会萤的", index: 7 }, { name: "免于哀伤", index: 8 }
    ];

    specialMotions.forEach(m => {
        const btn = document.createElement('button');
        btn.textContent = m.name;
        btn.style.cssText = 'display:block; width:100%; margin:3px 0; cursor:pointer; padding:4px;';
        btn.onclick = () => playMotionWithTimer("special", m.index);
        btnContainer.appendChild(btn);
    });

    const expressions = ["墨镜", "猫耳", "裂开", "鄙夷", "生气", "问号", "眼泪", "流汗", "呆愣", "开心"];
    expressions.forEach(name => {
        const btn = document.createElement('button');
        btn.textContent = name;
        btn.style.cssText = 'display:block; width:100%; margin:3px 0; cursor:pointer; padding:4px;';
        btn.onclick = () => setExpressionWithTimer(name);
        btnContainer.appendChild(btn);
    });
}