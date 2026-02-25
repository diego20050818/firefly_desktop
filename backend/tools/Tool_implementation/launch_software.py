"""
极简应用启动器 - 专为LLM调用设计
使用最直接的Windows数据源，无需复杂配置
"""

from pathlib import Path
import os
import winreg
from fuzzywuzzy import fuzz
import pypinyin
import re


class AppFinder:
    """单例模式的应用查找器"""
    _instance = None
    _apps_cache = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._apps_cache is None:
            self._refresh_apps()
    
    def _refresh_apps(self):
        """刷新应用列表"""
        self._apps_cache = {}
        
        # 数据源1: Compatibility Assistant Store（所有运行过的exe）
        try:
            reg_path = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                i = 0
                while True:
                    try:
                        exe_path_str, _, _ = winreg.EnumValue(key, i)
                        exe_path = Path(exe_path_str)
                        if exe_path.exists() and exe_path.suffix.lower() == '.exe':
                            self._apps_cache[exe_path.stem] = str(exe_path)
                        i += 1
                    except OSError:
                        break
        except:
            pass
        
        # 数据源2: 开始菜单快捷方式
        for start_path in [
            Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
            Path(os.environ.get('APPDATA', '')) / r"Microsoft\Windows\Start Menu\Programs"
        ]:
            if start_path.exists():
                for lnk in start_path.rglob('*.lnk'):
                    try:
                        target = self._get_lnk_target(lnk)
                        if target and Path(target).exists():
                            self._apps_cache[lnk.stem] = target
                    except:
                        continue
    
    def _get_lnk_target(self, lnk_path):
        """获取快捷方式目标"""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            return shell.CreateShortCut(str(lnk_path)).Targetpath
        except:
            return None
    
    def _score(self, query, app_name):
        """计算匹配分数"""
        # 标准化
        query = re.sub(r'[_\-\s]+', '', query.lower())
        app = re.sub(r'[_\-\s]+', '', app_name.lower())
        
        # 拼音
        try:
            query_py = ''.join(pypinyin.lazy_pinyin(query, style=pypinyin.NORMAL))
            app_py = ''.join(pypinyin.lazy_pinyin(app, style=pypinyin.NORMAL))
        except:
            query_py = query
            app_py = app
        
        # 计算分数
        return max(
            100 if query in app else 0,
            100 if query_py in app_py else 0,
            fuzz.ratio(query, app),
            fuzz.ratio(query_py, app_py),
            fuzz.partial_ratio(query, app) + 10,
            fuzz.partial_ratio(query_py, app_py) + 10
        )
    
    def find(self, query):
        """查找应用，返回最佳匹配"""
        best_match = None
        best_score = 0
        
        for app_name, exe_path in self._apps_cache.items():
            score = self._score(query, app_name)
            if score > best_score:
                best_score = score
                best_match = (app_name, exe_path)
        
        if best_score >= 40:  # 阈值
            return best_match
        return None
    
    def get_all(self):
        """获取所有应用"""
        return self._apps_cache


# ============= LLM调用的简单函数 =============

def find_app(app_name: str) -> dict:
    """
    查找应用程序
    
    Args:
        app_name: 应用名称（支持中英文、拼音）
        
    Returns:
        {
            "success": bool,
            "app_name": str or None,
            "path": str or None,
            "message": str
        }
    """
    finder = AppFinder()
    result = finder.find(app_name)
    
    if result:
        name, path = result
        return {
            "success": True,
            "app_name": name,
            "path": path,
            "message": f"找到应用: {name}"
        }
    else:
        return {
            "success": False,
            "app_name": None,
            "path": None,
            "message": f"未找到: {app_name}"
        }


def launch_app(app_name: str) -> dict:
    """
    查找并启动应用程序
    
    Args:
        app_name: 应用名称
        
    Returns:
        {
            "success": bool,
            "app_name": str or None,
            "path": str or None,
            "message": str
        }
    """
    result = find_app(app_name)
    
    if not result["success"]:
        return result
    
    try:
        os.startfile(result["path"])
        return {
            "success": True,
            "app_name": result["app_name"],
            "path": result["path"],
            "message": f"已启动: {result['app_name']}"
        }
    except Exception as e:
        return {
            "success": False,
            "app_name": result["app_name"],
            "path": result["path"],
            "message": f"启动失败: {str(e)}"
        }


def list_apps(filter_text: str = None) -> dict:
    """
    列出所有应用
    
    Args:
        filter_text: 可选的过滤文本
        
    Returns:
        {
            "success": bool,
            "count": int,
            "apps": [{"name": str, "path": str}, ...],
            "message": str
        }
    """
    finder = AppFinder()
    all_apps = finder.get_all()
    
    if filter_text:
        filtered = {}
        for name, path in all_apps.items():
            if finder._score(filter_text, name) >= 40:
                filtered[name] = path
        all_apps = filtered
    
    apps_list = [
        {"name": name, "path": path} 
        for name, path in sorted(all_apps.items())
    ]
    
    return {
        "success": True,
        "count": len(apps_list),
        "apps": apps_list,
        "message": f"共 {len(apps_list)} 个应用"
    }


# ============= 测试 =============

if __name__ == "__main__":
    # 测试1: 查找
    print("测试1: 查找VSCode")
    result = find_app("vscode")
    print(result)
    print()
    
    # 测试2: 查找中文应用
    print("测试2: 查找网易云")
    result = find_app("网易云")
    print(result)
    print()
    
    # 测试3: 拼音查找
    print("测试3: 拼音查找微信")
    result = find_app("微信")
    print(result)
    print()
    
    # # 测试4: 启动（注释掉，避免实际启动）
    # print("测试4: 启动应用")
    # result = launch_app("vscode")
    # print(result)
    
    # 测试5: 列出所有应用
    print("测试5: 列出所有应用（前10个）")
    result = list_apps()
    for app in result["apps"][:10]:
        print(f"  {app['name']}: {app['path']}")

# TODO 关于启动应用，我觉得最稳妥的方式还是先get_list,为了防止过多的应用超出模型的上下文，应该指定在开始程序的C:\ProgramData\Microsoft\Windows\Start Menu\Programs(或者指定的文件夹）中查找应用，而不应该在注册表中查找应用，这样既可以节省模型的上下文，也可以手动将常用的快捷键放入这个文件夹，然后launch_app，但是模型交互会比较复杂，我不知道mcp能不能把这两步操作原子化

# 参考代码：
"""
FastMCP Windows应用启动器 - LLM自主决策版本

设计理念：
1. list_apps: 返回应用列表给LLM
2. LLM根据用户输入 + 应用列表，自己决定启动哪个
3. launch_app: 精确启动（不做任何模糊匹配）

这样做的好处：
- LLM的语义理解能力远超模糊匹配算法
- LLM可以根据上下文做出最佳判断
- 代码简单，逻辑清晰
"""

from fastmcp import FastMCP
from pathlib import Path
import os
import win32com.client
from typing import List, Dict, Optional

mcp = FastMCP("Windows App Launcher")


def get_shortcut_target(lnk_path: Path) -> Optional[str]:
    """获取快捷方式的目标路径"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(lnk_path))
        target = shortcut.Targetpath
        return target if target and target.lower().endswith('.exe') else None
    except:
        return None


@mcp.tool()
def list_apps(
    custom_folders: List[str] | None = None,
    max_results: int = 100
) -> Dict[str, str]:
    """
    列出Windows开始菜单中的所有应用程序
    
    返回格式: {应用名称: exe完整路径}
    
    Args:
        custom_folders: 可选的自定义文件夹路径列表（如 ["D:/MyApps"]）
                       如果不提供，则扫描系统默认开始菜单路径
        max_results: 最大返回应用数量，防止超出上下文（默认100）
    
    Returns:
        字典，格式为 {应用名称: exe路径}，按应用名称排序
        
    Example:
        {
            "Chrome": "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "Visual Studio Code": "C:/Users/.../Code.exe",
            "微信": "C:/Program Files/Tencent/WeChat/WeChat.exe",
            "网易云音乐": "C:/Program Files/NetEase/CloudMusic/cloudmusic.exe"
        }
        
    Note:
        这个工具应该在用户请求启动应用时首先调用，
        然后根据用户的需求和返回的列表，决定要启动哪个应用
    """
    apps = {}
    
    # 默认扫描路径
    if custom_folders is None:
        scan_paths = [
            Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / 'Microsoft/Windows/Start Menu/Programs',
            Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs',
        ]
    else:
        scan_paths = [Path(p) for p in custom_folders]
    
    # 扫描所有快捷方式
    for start_path in scan_paths:
        if not start_path.exists():
            continue
        
        try:
            for lnk_file in start_path.rglob('*.lnk'):
                target = get_shortcut_target(lnk_file)
                if target:
                    app_name = lnk_file.stem
                    # 避免重复，保留第一个找到的
                    if app_name not in apps:
                        apps[app_name] = target
        except Exception as e:
            # 跳过无法访问的路径
            continue
    
    # 按名称排序
    sorted_apps = dict(sorted(apps.items()))
    
    # 限制返回数量
    if len(sorted_apps) > max_results:
        return dict(list(sorted_apps.items())[:max_results])
    
    return sorted_apps


@mcp.tool()
def launch_app(app_name: str, exe_path: str | None = None) -> Dict[str, any]:
    """
    启动指定的Windows应用程序（精确匹配，不做模糊匹配）
    
    Args:
        app_name: 应用名称（必须与list_apps返回的键完全一致）
        exe_path: 可选的exe完整路径。如果提供，将直接启动该路径；
                 如果不提供，将重新扫描列表查找该应用名称
    
    Returns:
        {
            "success": bool,
            "message": str,
            "app_name": str,
            "exe_path": str | None
        }
    
    Example:
        # 推荐方式：直接传入从list_apps获取的路径
        launch_app("Chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe")
        
        # 或者只传应用名（会重新扫描）
        launch_app("Chrome")
    
    Note:
        建议先调用list_apps获取应用列表，然后使用列表中的确切名称和路径
        这样可以避免二次扫描，提高效率
    """
    try:
        # 如果提供了路径，直接启动
        if exe_path:
            exe_file = Path(exe_path)
            
            if not exe_file.exists():
                return {
                    "success": False,
                    "message": f"路径不存在: {exe_path}",
                    "app_name": app_name,
                    "exe_path": exe_path
                }
            
            if not exe_file.suffix.lower() == '.exe':
                return {
                    "success": False,
                    "message": f"不是有效的exe文件: {exe_path}",
                    "app_name": app_name,
                    "exe_path": exe_path
                }
            
            # 启动应用
            os.startfile(exe_file)
            
            return {
                "success": True,
                "message": f"已启动 {app_name}",
                "app_name": app_name,
                "exe_path": exe_path
            }
        
        # 如果没有提供路径，重新扫描查找
        apps = list_apps()
        
        if app_name not in apps:
            return {
                "success": False,
                "message": f"未找到应用 '{app_name}'。请先调用list_apps查看可用应用列表",
                "app_name": app_name,
                "exe_path": None
            }
        
        exe_path = apps[app_name]
        exe_file = Path(exe_path)
        
        if not exe_file.exists():
            return {
                "success": False,
                "message": f"应用路径不存在: {exe_path}",
                "app_name": app_name,
                "exe_path": exe_path
            }
        
        # 启动应用
        os.startfile(exe_file)
        
        return {
            "success": True,
            "message": f"已启动 {app_name}",
            "app_name": app_name,
            "exe_path": exe_path
        }
        
    except PermissionError:
        return {
            "success": False,
            "message": f"没有权限启动应用: {app_name}",
            "app_name": app_name,
            "exe_path": exe_path
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"启动失败: {str(e)}",
            "app_name": app_name,
            "exe_path": exe_path
        }


if __name__ == "__main__":
    # 运行MCP服务器
    mcp.run()

