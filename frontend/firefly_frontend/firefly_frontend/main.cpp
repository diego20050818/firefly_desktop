#include <windows.h>
#include <wrl.h>
#include <wil/com.h>
#include <WebView2.h>
#include <string>

using namespace Microsoft::WRL;

// 窗口过程函数
LRESULT CALLBACK WndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam) {
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProc(hWnd, message, wParam, lParam);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    // 1. 注册窗口类
    WNDCLASSEX wcex = { sizeof(WNDCLASSEX), CS_HREDRAW | CS_VREDRAW, WndProc, 0, 0, hInstance, NULL, NULL, NULL, NULL, L"FireflyDesktop", NULL };
    RegisterClassEx(&wcex);

    // 2. 创建完全透明、无边框、置顶的窗口
    HWND hWnd = CreateWindowEx(
        WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST,
        L"FireflyDesktop", L"Firefly", WS_POPUP,
        0, 0, 1920, 1080, // 覆盖全屏，依靠点击穿透不影响其他操作
        NULL, NULL, hInstance, NULL
    );
    SetLayeredWindowAttributes(hWnd, RGB(0, 0, 0), 0, LWA_COLORKEY); // 黑色设为透明
    ShowWindow(hWnd, nCmdShow);

    // 3. 初始化 WebView2 环境
    CreateCoreWebView2EnvironmentWithOptions(nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [hWnd](HRESULT result, ICoreWebView2Environment* env) -> HRESULT {
                env->CreateCoreWebView2Controller(hWnd, Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                    [hWnd](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                        if (controller != nullptr) {
                            ICoreWebView2* webview;
                            controller->get_CoreWebView2(&webview);

                            // 关键：让 WebView 控件本身也透明
                            controller->put_IsVisible(TRUE);

                            // 【关键】导航到你的 HTML 前端文件
                            // 请改成你项目的实际 index.html 绝对路径
                            webview->Navigate(L"E:/firefly_desktop/frontend/index.html");
                        }
                        return S_OK;
                    }).Get());
                return S_OK;
            }).Get());

    // 4. 消息循环
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return (int)msg.wParam;
}