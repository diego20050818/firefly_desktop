#define CHAT_PAGE_PATH L"/pages/chat/index.html"
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

wil::com_ptr<ICoreWebView2Controller> g_controller;
wil::com_ptr<ICoreWebView2> g_webview;

const int CARD_W = 420;
const int CARD_H = 560;
const int SHADOW_PAD = 40;              // 四周留给阴影的空间
const int WIN_W = CARD_W + SHADOW_PAD * 2;
const int WIN_H = CARD_H + SHADOW_PAD * 2;

LRESULT CALLBACK WndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {

    case WM_SIZE:
        if (g_controller) {
            RECT bounds;
            GetClientRect(hWnd, &bounds);
            g_controller->put_Bounds(bounds);
        }
        break;

    case WM_ERASEBKGND: {
        HDC hdc = (HDC)wParam;
        RECT rc;
        GetClientRect(hWnd, &rc);
        HBRUSH brush = CreateSolidBrush(RGB(0, 0, 0));
        FillRect(hdc, &rc, brush);
        DeleteObject(brush);
        return 1;
    }

                      // ★ 透明 padding 区域鼠标穿透
    case WM_NCHITTEST: {
        POINT pt = { GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) };
        ScreenToClient(hWnd, &pt);
        RECT rc;
        GetClientRect(hWnd, &rc);
        // 鼠标在 padding 区域内 → 穿透到桌面
        if (pt.x < SHADOW_PAD || pt.y < SHADOW_PAD ||
            pt.x > rc.right - SHADOW_PAD ||
            pt.y > rc.bottom - SHADOW_PAD) {
            return HTTRANSPARENT;
        }
        return HTCLIENT;
    }

    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProc(hWnd, message, wParam, lParam);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {

    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) {
        MessageBox(NULL, L"COM 初始化失败", L"Error", MB_OK);
        return -1;
    }

    WNDCLASSEX wcex = {};
    wcex.cbSize = sizeof(WNDCLASSEX);
    wcex.lpfnWndProc = WndProc;
    wcex.hInstance = hInstance;
    wcex.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
    wcex.lpszClassName = L"FireflyDesktop";
    RegisterClassEx(&wcex);

    // 右下角定位
    int screenW = GetSystemMetrics(SM_CXSCREEN);
    int screenH = GetSystemMetrics(SM_CYSCREEN);
    int posX = screenW - WIN_W - 40 + SHADOW_PAD; // 抵消 padding 视觉偏移
    int posY = screenH - WIN_H - 60 + SHADOW_PAD;

    HWND hWnd = CreateWindowEx(
        WS_EX_TOPMOST | WS_EX_NOREDIRECTIONBITMAP,
        L"FireflyDesktop", L"Firefly",
        WS_POPUP,
        posX, posY, WIN_W, WIN_H,
        NULL, NULL, hInstance, NULL
    );

    if (!hWnd) { CoUninitialize(); return -1; }

    MARGINS margins = { -1 };
    DwmExtendFrameIntoClientArea(hWnd, &margins);

    ShowWindow(hWnd, nCmdShow);
    UpdateWindow(hWnd);

    hr = CreateCoreWebView2EnvironmentWithOptions(nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [hWnd](HRESULT result, ICoreWebView2Environment* env) -> HRESULT {
                if (FAILED(result) || !env) return result;

                env->CreateCoreWebView2Controller(hWnd,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [hWnd](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            if (FAILED(result) || !controller) return result;

                            g_controller = controller;
                            g_controller->get_CoreWebView2(&g_webview);

                            // WebView2 背景透明
                            wil::com_ptr<ICoreWebView2Controller2> ctrl2;
                            g_controller->QueryInterface(IID_PPV_ARGS(&ctrl2));
                            if (ctrl2) {
                                COREWEBVIEW2_COLOR transparent = { 0, 0, 0, 0 };
                                ctrl2->put_DefaultBackgroundColor(transparent);
                            }

                            // ★ 显式开启 Web 消息通道
                            wil::com_ptr<ICoreWebView2Settings> settings;
                            g_webview->get_Settings(&settings);
                            if (settings) {
                                settings->put_IsWebMessageEnabled(TRUE);
                                settings->put_AreDefaultContextMenusEnabled(FALSE);
                            }

                            RECT bounds;
                            GetClientRect(hWnd, &bounds);
                            g_controller->put_Bounds(bounds);
                            g_controller->put_IsVisible(TRUE);

                            // ★ 接收 JS 消息
                            g_webview->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [hWnd](ICoreWebView2* sender, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        wil::unique_cotaskmem_string raw;
                                        args->TryGetWebMessageAsString(&raw);
                                        if (!raw) return S_OK;

                                        std::wstring msg = raw.get();
                                        OutputDebugString((L"Received message: " + msg + L"\n").c_str());

                                        if (msg == L"drag") {
                                            ReleaseCapture();
                                            SendMessage(hWnd, WM_NCLBUTTONDOWN, HTCAPTION, 0);
                                        }
                                        else if (msg == L"close") {
                                            PostMessage(hWnd, WM_CLOSE, 0, 0);
                                        }
                                        else if (msg == L"minimize") {
                                            ShowWindow(hWnd, SW_MINIMIZE);
                                        }
                                        return S_OK;
                                    }).Get(), nullptr);

                            // 加载本地 HTML
                            wchar_t buffer[MAX_PATH];
                            GetModuleFileName(NULL, buffer, MAX_PATH);
                            std::wstring exePath(buffer);
                            exePath = exePath.substr(0, exePath.find_last_of(L"\\/"));

                            // 由于构建步骤会复制文件到输出目录，这里可以直接使用相对路径
                            std::wstring htmlPath = L"file:///" + exePath + CHAT_PAGE_PATH;

                            g_webview->Navigate(htmlPath.c_str());

                            return S_OK;
                        }).Get());
                return S_OK;
            }).Get());

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    g_webview = nullptr;
    g_controller = nullptr;
    CoUninitialize();
    return (int)msg.wParam;
}