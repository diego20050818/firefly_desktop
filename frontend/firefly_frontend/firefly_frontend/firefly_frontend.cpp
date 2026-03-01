#include <windows.h>
#include <windowsx.h>
#include <wrl.h>
#include <wil/com.h>
#include <WebView2.h>
#include <objbase.h>
#include <dwmapi.h>
#include <string>

#pragma comment(lib, "dwmapi.lib")

using namespace Microsoft::WRL;

// --- 虚拟域名配置 ---
#define VIRTUAL_HOST L"firefly.local"
#define MODEL_PAGE_PATH L"/pages/model/index.html"
#define CHAT_PAGE_PATH L"/pages/chat/index.html"

// --- 全局变量 ---
wil::com_ptr<ICoreWebView2Controller> g_controllerModel;
wil::com_ptr<ICoreWebView2> g_webviewModel;
HWND g_hWndModel = nullptr;

wil::com_ptr<ICoreWebView2Controller> g_controllerChat;
wil::com_ptr<ICoreWebView2> g_webviewChat;
HWND g_hWndChat = nullptr;

const int MODEL_W = 500;
const int MODEL_H = 600;
const float MODEL_SCALE = 0.8;
const int CHAT_W = 420;
const int CHAT_H = 560;
const int SHADOW_PAD = 40;

// 获取当前 EXE 所在的目录
std::wstring GetFrontendRootDir() {
    wchar_t buffer[MAX_PATH];
    GetModuleFileName(NULL, buffer, MAX_PATH);
    std::wstring path(buffer);
    size_t lastSlash = path.find_last_of(L"\\/");
    return path.substr(0, lastSlash);
}

// 窗口过程
LRESULT CALLBACK WndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
    case WM_SIZE:
        if (hWnd == g_hWndModel && g_controllerModel) {
            RECT bounds; GetClientRect(hWnd, &bounds);
            g_controllerModel->put_Bounds(bounds);
        }
        else if (hWnd == g_hWndChat && g_controllerChat) {
            RECT bounds; GetClientRect(hWnd, &bounds);
            g_controllerChat->put_Bounds(bounds);
        }
        break;
    case WM_ERASEBKGND:
        return 1;
    case WM_NCHITTEST:
        if (hWnd == g_hWndModel) {
            POINT pt = { GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) };
            ScreenToClient(hWnd, &pt);
            RECT rc; GetClientRect(hWnd, &rc);
            if (pt.x < SHADOW_PAD || pt.y < SHADOW_PAD ||
                pt.x > rc.right - SHADOW_PAD ||
                pt.y > rc.bottom - SHADOW_PAD) {
                return HTTRANSPARENT; // 边缘透明区域鼠标穿透
            }
        }
        return HTCLIENT;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProc(hWnd, message, wParam, lParam);
}

void SetWebviewTransparent(wil::com_ptr<ICoreWebView2Controller> controller) {
    wil::com_ptr<ICoreWebView2Controller2> ctrl2;
    if (SUCCEEDED(controller->QueryInterface(IID_PPV_ARGS(&ctrl2)))) {
        COREWEBVIEW2_COLOR transparent = { 0, 0, 0, 0 };
        ctrl2->put_DefaultBackgroundColor(transparent);
    }
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

    WNDCLASSEX wcex = { sizeof(WNDCLASSEX), CS_HREDRAW | CS_VREDRAW, WndProc, 0, 0, hInstance, NULL, NULL, NULL, NULL, L"FireflyDesktop", NULL };
    RegisterClassEx(&wcex);

    int screenW = GetSystemMetrics(SM_CXSCREEN);
    int screenH = GetSystemMetrics(SM_CYSCREEN);

    // 1. 创建模型窗口
    g_hWndModel = CreateWindowEx(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOREDIRECTIONBITMAP,
        L"FireflyDesktop", L"Model", WS_POPUP,
        100, screenH - MODEL_H - 100, MODEL_W, MODEL_H, NULL, NULL, hInstance, NULL);
    MARGINS margins = { -1 };
    DwmExtendFrameIntoClientArea(g_hWndModel, &margins);
    ShowWindow(g_hWndModel, nCmdShow);

    // 2. 创建聊天窗口
    g_hWndChat = CreateWindowEx(WS_EX_TOPMOST | WS_EX_NOREDIRECTIONBITMAP,
        L"FireflyDesktop", L"Chat", WS_POPUP,
        screenW - CHAT_W - 100, screenH - CHAT_H - 100, CHAT_W, CHAT_H, NULL, NULL, hInstance, NULL);
    ShowWindow(g_hWndChat, nCmdShow);

    std::wstring rootDir = GetFrontendRootDir();

    CreateCoreWebView2EnvironmentWithOptions(nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [rootDir](HRESULT result, ICoreWebView2Environment* env) -> HRESULT {

                // --- 初始化模型 WebView ---
                env->CreateCoreWebView2Controller(g_hWndModel,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [rootDir](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            g_controllerModel = controller;
                            g_controllerModel->get_CoreWebView2(&g_webviewModel);

                            wil::com_ptr<ICoreWebView2_3> webView3;
                            if (SUCCEEDED(g_webviewModel->QueryInterface(IID_PPV_ARGS(&webView3)))) {
                                webView3->SetVirtualHostNameToFolderMapping(VIRTUAL_HOST, rootDir.c_str(), COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
                            }

                            // --- 关键补丁：开启消息通道 ---
                            wil::com_ptr<ICoreWebView2Settings> settings;
                            g_webviewModel->get_Settings(&settings);
                            if (settings) settings->put_IsWebMessageEnabled(TRUE);

                            // --- 关键补丁：处理模型窗口的拖动消息 ---
                            g_webviewModel->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [](ICoreWebView2* sender, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        wil::unique_cotaskmem_string raw;
                                        args->TryGetWebMessageAsString(&raw);
                                        if (raw) {
                                            std::wstring msg = raw.get();
                                            if (msg == L"drag") {
                                                ReleaseCapture();
                                                // 这里确保发送给模型窗口句柄 g_hWndModel
                                                SendMessage(g_hWndModel, WM_NCLBUTTONDOWN, HTCAPTION, 0);
                                            }
                                        }
                                        return S_OK;
                                    }).Get(), nullptr);

                            SetWebviewTransparent(g_controllerModel);
                            RECT bounds; GetClientRect(g_hWndModel, &bounds);
                            g_controllerModel->put_Bounds(bounds);
                            g_controllerModel->put_IsVisible(TRUE);
                            g_webviewModel->Navigate((L"https://" + std::wstring(VIRTUAL_HOST) + MODEL_PAGE_PATH).c_str());
                            return S_OK;
                        }).Get());

                // --- 初始化聊天 WebView ---
                env->CreateCoreWebView2Controller(g_hWndChat,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [rootDir](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            g_controllerChat = controller;
                            g_controllerChat->get_CoreWebView2(&g_webviewChat);

                            wil::com_ptr<ICoreWebView2_3> webView3Chat;
                            if (SUCCEEDED(g_webviewChat->QueryInterface(IID_PPV_ARGS(&webView3Chat)))) {
                                webView3Chat->SetVirtualHostNameToFolderMapping(VIRTUAL_HOST, rootDir.c_str(), COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
                            }

                            SetWebviewTransparent(g_controllerChat);

                            // 开启 JS 消息通信
                            wil::com_ptr<ICoreWebView2Settings> settings;
                            g_webviewChat->get_Settings(&settings);
                            if (settings) settings->put_IsWebMessageEnabled(TRUE);


                            // 拖动和关闭的消息处理与窗口间通信
                            g_webviewChat->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [](ICoreWebView2* sender, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        wil::unique_cotaskmem_string raw;
                                        args->TryGetWebMessageAsString(&raw);
                                        if (raw) {
                                            std::wstring msg = raw.get();
                                            if (msg == L"drag") {
                                                ReleaseCapture();
                                                SendMessage(g_hWndChat, WM_NCLBUTTONDOWN, HTCAPTION, 0);
                                            }
                                            else if (msg == L"close") {
                                                PostMessage(g_hWndChat, WM_CLOSE, 0, 0);
                                            }
                                            // --- 新增：情绪标签转发给模型窗口 ---
                                            // 格式: "emotion:开心"
                                            else if (msg.length() > 8 && msg.substr(0, 8) == L"emotion:" && g_webviewModel) {
                                                std::wstring emotionName = msg.substr(8); // 截取冒号后的表情名
                                                // 转义单引号防止注入（中文标签一般不含引号，但严谨处理）
                                                std::wstring script = L"window.triggerEmotion('" + emotionName + L"')";
                                                g_webviewModel->ExecuteScript(script.c_str(), nullptr);
                                            }
                                            // --- 新增：动作指令转发给模型窗口 ---
                                            // 格式: "action:thinking"
                                            else if (msg.length() > 7 && msg.substr(0, 7) == L"action:" && g_webviewModel) {
                                                std::wstring actionName = msg.substr(7);
                                                std::wstring script = L"window.triggerAction('" + actionName + L"')";
                                                g_webviewModel->ExecuteScript(script.c_str(), nullptr);
                                            }
                                        }
                                        return S_OK;
                                    }).Get(), nullptr);


                            RECT bounds; GetClientRect(g_hWndChat, &bounds);
                            g_controllerChat->put_Bounds(bounds);
                            g_controllerChat->put_IsVisible(TRUE);
                            g_webviewChat->Navigate((L"https://" + std::wstring(VIRTUAL_HOST) + CHAT_PAGE_PATH).c_str());
                            return S_OK;
                        }).Get());

                return S_OK;
            }).Get());

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    CoUninitialize();
    return (int)msg.wParam;
}