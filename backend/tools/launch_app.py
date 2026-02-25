# tools/launch_app.py
"""
MCP 服务：提供本地工具调用能力
"""
from fastmcp import FastMCP
import subprocess
import platform

mcp = FastMCP(
    name="Local Tools Service",
    version="0.1.0",
    # description="提供本地应用启动、系统命令等工具"
)

@mcp.tool
def add(a: int, b: int) -> int:
    """将两个数字相加"""
    return a + b

@mcp.tool
def open_application(app_name: str) -> str:
    """在本地计算机上打开应用程序"""
    system = platform.system()
    app_map = {
        "notepad": {
            "Windows": "notepad.exe",
            "Linux": "gedit",
            "Darwin": "open -a TextEdit"
        },
        "calculator": {
            "Windows": "calc.exe", 
            "Linux": "gnome-calculator",
            "Darwin": "open -a Calculator"
        },
        "browser": {
            "Windows": "start https://www.google.com",
            "Linux": "xdg-open https://www.google.com",
            "Darwin": "open https://www.google.com"
        }
    }
    
    if app_name not in app_map:
        return f"不支持的应用: {app_name}"
    
    cmd = app_map[app_name][system]
    try:
        subprocess.Popen(cmd, shell=True)
        return f"已启动应用: {app_name}"
    except Exception as e:
        return f"启动失败: {str(e)}"
