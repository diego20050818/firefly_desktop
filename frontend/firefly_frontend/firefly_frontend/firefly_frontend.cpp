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
#define SETTINGS_PAGE_PATH L"/pages/settings/index.html"

// --- 全局变量 ---
wil::com_ptr<ICoreWebView2Controller> g_controllerModel;
wil::com_ptr<ICoreWebView2> g_webviewModel;
HWND g_hWndModel = nullptr;

wil::com_ptr<ICoreWebView2Controller> g_controllerChat;
wil::com_ptr<ICoreWebView2> g_webviewChat;
HWND g_hWndChat = nullptr;

wil::com_ptr<ICoreWebView2Controller> g_controllerSettings;
wil::com_ptr<ICoreWebView2> g_webviewSettings;
HWND g_hWndSettings = nullptr;

const int MODEL_W = 500;
const int MODEL_H = 600;
const int CHAT_W = 420;
const int CHAT_H = 600;
const int SETTINGS_W = 800;
const int SETTINGS_H = 600;
const int SHADOW_PAD = 40;
const int RESIZE_BORDER = 8; // 允许调节大小的边框宽度

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
        else if (hWnd == g_hWndSettings && g_controllerSettings) {
            RECT bounds; GetClientRect(hWnd, &bounds);
            g_controllerSettings->put_Bounds(bounds);
        }
        break;
    case WM_ERASEBKGND:
        return 1;
    case WM_NCHITTEST: {
        POINT pt = { GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) };
        ScreenToClient(hWnd, &pt);
        RECT rc; GetClientRect(hWnd, &rc);

        // 如果是模型窗口，保持原有的阴影区域点击穿透逻辑（实际上在WS_EX_LAYERED下，非零像素会自动拦截鼠标）
        // 但为了严谨，我们先处理边框逻辑
        if (hWnd == g_hWndChat || hWnd == g_hWndSettings) {
             // 检查是否在边缘以进行缩放
            if (pt.y < RESIZE_BORDER) {
                if (pt.x < RESIZE_BORDER) return HTTOPLEFT;
                if (pt.x > rc.right - RESIZE_BORDER) return HTTOPRIGHT;
                return HTTOP;
            }
            if (pt.y > rc.bottom - RESIZE_BORDER) {
                if (pt.x < RESIZE_BORDER) return HTBOTTOMLEFT;
                if (pt.x > rc.right - RESIZE_BORDER) return HTBOTTOMRIGHT;
                return HTBOTTOM;
            }
            if (pt.x < RESIZE_BORDER) return HTLEFT;
            if (pt.x > rc.right - RESIZE_BORDER) return HTRIGHT;
        }

        // 模型窗口的阴影穿透
        if (hWnd == g_hWndModel) {
            if (pt.x < SHADOW_PAD || pt.y < SHADOW_PAD ||
                pt.x > rc.right - SHADOW_PAD ||
                pt.y > rc.bottom - SHADOW_PAD) {
                return HTTRANSPARENT; 
            }
        }
        
        return HTCLIENT;
    }
    case WM_CLOSE:
        if (hWnd == g_hWndSettings) {
            ShowWindow(g_hWndSettings, SW_HIDE);
            return 0; // 不销毁
        }
        break;
    case WM_DESTROY:
        if (hWnd == g_hWndChat || hWnd == g_hWndModel) {
            PostQuitMessage(0);
        }
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

// 帮助函数：初始化 WebView2 设置并添加常用消息处理
void SetupCommonWebView(wil::com_ptr<ICoreWebView2> webview, HWND hWnd) {
    if (!webview) return;

    wil::com_ptr<ICoreWebView2Settings> settings;
    webview->get_Settings(&settings);
    if (settings) {
        settings->put_IsWebMessageEnabled(TRUE);
        settings->put_IsZoomControlEnabled(FALSE);
        settings->put_IsStatusBarEnabled(FALSE);
    }

    webview->add_WebMessageReceived(
        Callback<ICoreWebView2WebMessageReceivedEventHandler>(
            [hWnd](ICoreWebView2* sender, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                wil::unique_cotaskmem_string raw;
                args->TryGetWebMessageAsString(&raw);
                if (raw) {
                    std::wstring msg = raw.get();
                    if (msg == L"drag") {
                        ReleaseCapture();
                        SendMessage(hWnd, WM_NCLBUTTONDOWN, HTCAPTION, 0);
                    }
                    else if (msg == L"close") {
                        SendMessage(hWnd, WM_CLOSE, 0, 0);
                    }
                    else if (msg == L"open-settings") {
                        if (g_hWndSettings) {
                            ShowWindow(g_hWndSettings, SW_SHOW);
                            SetForegroundWindow(g_hWndSettings);
                        }
                    }
                    else if (msg.length() > 8 && msg.substr(0, 8) == L"emotion:" && g_webviewModel) {
                        g_webviewModel->ExecuteScript((L"window.triggerEmotion('" + msg.substr(8) + L"')").c_str(), nullptr);
                    }
                    else if (msg.length() > 7 && msg.substr(0, 7) == L"action:" && g_webviewModel) {
                        g_webviewModel->ExecuteScript((L"window.triggerAction('" + msg.substr(7) + L"')").c_str(), nullptr);
                    }
                }
                return S_OK;
            }).Get(), nullptr);
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
    g_hWndChat = CreateWindowEx(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOREDIRECTIONBITMAP,
        L"FireflyDesktop", L"Chat", WS_POPUP,
        screenW - CHAT_W - 100, screenH - CHAT_H - 100, CHAT_W, CHAT_H, NULL, NULL, hInstance, NULL);
    DwmExtendFrameIntoClientArea(g_hWndChat, &margins);
    ShowWindow(g_hWndChat, nCmdShow);

    // 3. 创建设置窗口 (默认隐藏)
    g_hWndSettings = CreateWindowEx(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOREDIRECTIONBITMAP,
        L"FireflyDesktop", L"Settings", WS_POPUP,
        (screenW - SETTINGS_W) / 2, (screenH - SETTINGS_H) / 2, SETTINGS_W, SETTINGS_H, NULL, NULL, hInstance, NULL);
    DwmExtendFrameIntoClientArea(g_hWndSettings, &margins);
    // ShowWindow(g_hWndSettings, SW_HIDE);

    std::wstring rootDir = GetFrontendRootDir();

    CreateCoreWebView2EnvironmentWithOptions(nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [rootDir](HRESULT result, ICoreWebView2Environment* env) -> HRESULT {

                // --- 模型 WebView ---
                env->CreateCoreWebView2Controller(g_hWndModel,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [rootDir](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            g_controllerModel = controller;
                            g_controllerModel->get_CoreWebView2(&g_webviewModel);
                            wil::com_ptr<ICoreWebView2_3> webView3;
                            if (SUCCEEDED(g_webviewModel->QueryInterface(IID_PPV_ARGS(&webView3)))) {
                                webView3->SetVirtualHostNameToFolderMapping(VIRTUAL_HOST, rootDir.c_str(), COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
                            }
                            SetupCommonWebView(g_webviewModel, g_hWndModel);
                            SetWebviewTransparent(g_controllerModel);
                            RECT bounds; GetClientRect(g_hWndModel, &bounds);
                            g_controllerModel->put_Bounds(bounds);
                            g_controllerModel->put_IsVisible(TRUE);
                            g_webviewModel->Navigate((L"https://" + std::wstring(VIRTUAL_HOST) + MODEL_PAGE_PATH).c_str());
                            return S_OK;
                        }).Get());

                // --- 聊天 WebView ---
                env->CreateCoreWebView2Controller(g_hWndChat,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [rootDir](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            g_controllerChat = controller;
                            g_controllerChat->get_CoreWebView2(&g_webviewChat);
                            wil::com_ptr<ICoreWebView2_3> webView3Chat;
                            if (SUCCEEDED(g_webviewChat->QueryInterface(IID_PPV_ARGS(&webView3Chat)))) {
                                webView3Chat->SetVirtualHostNameToFolderMapping(VIRTUAL_HOST, rootDir.c_str(), COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
                            }
                            SetupCommonWebView(g_webviewChat, g_hWndChat);
                            SetWebviewTransparent(g_controllerChat);
                            RECT bounds; GetClientRect(g_hWndChat, &bounds);
                            g_controllerChat->put_Bounds(bounds);
                            g_controllerChat->put_IsVisible(TRUE);
                            g_webviewChat->Navigate((L"https://" + std::wstring(VIRTUAL_HOST) + CHAT_PAGE_PATH).c_str());
                            return S_OK;
                        }).Get());

                // --- 设置 WebView ---
                env->CreateCoreWebView2Controller(g_hWndSettings,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [rootDir](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            g_controllerSettings = controller;
                            g_controllerSettings->get_CoreWebView2(&g_webviewSettings);
                            wil::com_ptr<ICoreWebView2_3> webView3Settings;
                            if (SUCCEEDED(g_webviewSettings->QueryInterface(IID_PPV_ARGS(&webView3Settings)))) {
                                webView3Settings->SetVirtualHostNameToFolderMapping(VIRTUAL_HOST, rootDir.c_str(), COREWEBVIEW2_HOST_RESOURCE_ACCESS_KIND_ALLOW);
                            }
                            SetupCommonWebView(g_webviewSettings, g_hWndSettings);
                            SetWebviewTransparent(g_controllerSettings);
                            RECT bounds; GetClientRect(g_hWndSettings, &bounds);
                            g_controllerSettings->put_Bounds(bounds);
                            g_controllerSettings->put_IsVisible(TRUE);
                            g_webviewSettings->Navigate((L"https://" + std::wstring(VIRTUAL_HOST) + SETTINGS_PAGE_PATH).c_str());
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
