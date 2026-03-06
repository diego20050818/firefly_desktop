# tools/launch_app.py
"""
MCP 服务：提供本地工具调用能力
"""
from fastmcp import FastMCP
import subprocess
import platform
from pathlib import Path
import os
from typing import List, Dict

mcp = FastMCP(
    name="Local Tools Service",
    version="0.1.0",
    # description="提供本地应用启动、系统命令等工具"
)


@mcp.tool
def list_start_menu_apps() -> Dict[str, List[str]]:
    """从开始菜单中获取所有可执行程序和快捷方式路径"""
    system = platform.system()
    
    if system != "Windows":
        return {"error": f"此功能仅支持Windows系统，当前系统为: {system}"}
    
    apps = {
        "programs_public": [],
        "programs_user": []
    }
    
    # 获取公共开始菜单程序路径
    public_programs_path = Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if public_programs_path.exists():
        apps["programs_public"] = _scan_directory_for_apps(public_programs_path)
    
    # 获取用户开始菜单程序路径
    user_programs_path = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if user_programs_path.exists():
        apps["programs_user"] = _scan_directory_for_apps(user_programs_path)
    
    return apps


def _scan_directory_for_apps(directory: Path) -> List[str]:
    """扫描目录及其子目录中的exe和lnk文件"""
    apps = []
    # 使用 rglob 递归搜索所有子目录中的 .exe 和 .lnk 文件
    for file_path in directory.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in ['.exe', '.lnk']:
            apps.append(str(file_path))
    return apps


@mcp.tool
def launch_application_by_path(app_path: str) -> str:
    """使用subprocess启动指定路径的应用程序"""
    file_path = Path(app_path)
    if not file_path.exists():
        return f"应用路径不存在: {app_path}"
    
    try:
        # 检查是否是有效的可执行文件
        if file_path.suffix.lower() == '.lnk':
            # 对于快捷方式，在Windows上使用start命令
            subprocess.Popen(['cmd', '/c', 'start', '', str(file_path)], shell=False)
        else:
            subprocess.Popen([str(file_path)], shell=False)
        
        return f"已启动应用: {file_path.name}"
    except Exception as e:
        return f"启动失败: {str(e)}"