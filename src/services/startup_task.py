import os
import platform
import subprocess
import sys
from dataclasses import dataclass

from src.app_info import APP_NAME


TASK_NAME = APP_NAME
STARTUP_SCRIPT_NAME = f"{APP_NAME}开机启动.vbs"
RUN_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


@dataclass
class StartupTaskResult:
    success: bool
    title: str
    message: str


def get_startup_target():
    if getattr(sys, "frozen", False):
        executable_path = sys.executable
        arguments = ""
        working_directory = os.path.dirname(executable_path)
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        executable_path = sys.executable
        arguments = os.path.join(project_root, "main.py")
        working_directory = project_root

    return executable_path, arguments, working_directory


def get_user_startup_folder():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def build_registry_startup_command(executable_path, arguments=""):
    command = f'"{executable_path}"'
    if arguments:
        command += f' "{arguments}"'
    return command


def _get_winreg():
    import winreg

    return winreg


def _read_registry_command():
    winreg = _get_winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, TASK_NAME)
            return str(value or "")
    except FileNotFoundError:
        return ""


def _write_registry_command(command):
    winreg = _get_winreg()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_PATH) as key:
        winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, command)


def _delete_registry_command():
    winreg = _get_winreg()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, TASK_NAME)
    except FileNotFoundError:
        pass


def _legacy_vbs_path():
    startup_folder = get_user_startup_folder()
    if not startup_folder:
        return None
    return os.path.join(startup_folder, STARTUP_SCRIPT_NAME)


def _remove_legacy_vbs():
    script_path = _legacy_vbs_path()
    if script_path and os.path.exists(script_path):
        os.remove(script_path)


def _task_not_found(output):
    normalized = str(output or "").lower()
    return any(
        marker in normalized
        for marker in (
            "cannot find",
            "not found",
            "does not exist",
            "找不到",
            "不存在",
        )
    )


def _remove_legacy_scheduled_task():
    completed = subprocess.run(
        ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    detail = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode != 0 and not _task_not_found(detail):
        raise RuntimeError(detail or "删除旧任务计划失败")


def _cleanup_legacy_startup_entries():
    _remove_legacy_vbs()
    _remove_legacy_scheduled_task()


def get_startup_status():
    if platform.system() != "Windows":
        return "disabled"
    executable_path, arguments, _working_directory = get_startup_target()
    expected = build_registry_startup_command(executable_path, arguments)
    try:
        stored = _read_registry_command()
    except OSError:
        return "repair"
    if stored:
        return "enabled" if stored.strip().casefold() == expected.casefold() else "repair"
    legacy_vbs = _legacy_vbs_path()
    return "repair" if legacy_vbs and os.path.exists(legacy_vbs) else "disabled"


def startup_action_label(status):
    return {
        "enabled": "关闭开机自启",
        "repair": "修复开机自启",
    }.get(status, "启用开机自启")


def enable_startup_task():
    if platform.system() != "Windows":
        return StartupTaskResult(
            success=False,
            title="当前系统不支持",
            message="一键开机自启只支持 Windows 客户端。",
        )

    executable_path, arguments, _working_directory = get_startup_target()
    if not os.path.exists(executable_path):
        return StartupTaskResult(
            success=False,
            title="未找到程序文件",
            message=f"找不到要自启的程序：{executable_path}",
        )

    try:
        _cleanup_legacy_startup_entries()
    except Exception as exc:
        return StartupTaskResult(
            success=False,
            title="开机自启迁移失败",
            message=(
                "清理旧版开机启动项失败，尚未写入新的注册表启动项。\n"
                f"具体原因：{exc}\n"
                "请确认安全软件没有阻止删除旧任务计划或 VBS。"
            ),
        )

    try:
        _write_registry_command(
            build_registry_startup_command(executable_path, arguments)
        )
    except Exception as exc:
        return StartupTaskResult(
            success=False,
            title="开机自启设置失败",
            message=(
                "无法写入当前用户的 Windows 开机启动项。\n"
                f"具体原因：{exc}\n"
                "请确认安全软件没有阻止本程序修改开机启动设置。"
            ),
        )

    return StartupTaskResult(
        success=True,
        title="开机自启已启用",
        message=(
            "已写入当前用户的 Windows 注册表开机启动项，无需管理员权限。\n"
            f"程序路径：{executable_path}\n"
            "安装版会保持固定程序路径；如果使用 ZIP 便携版，移动目录后请重新启用。\n"
            "旧 VBS 和旧任务计划已清理。"
        ),
    )


def disable_startup_task():
    if platform.system() != "Windows":
        return StartupTaskResult(
            success=False,
            title="当前系统不支持",
            message="开机自启设置只支持 Windows 客户端。",
        )
    try:
        _delete_registry_command()
        _cleanup_legacy_startup_entries()
    except Exception as exc:
        return StartupTaskResult(
            success=False,
            title="关闭开机自启失败",
            message=f"未能完整删除 Windows 开机启动项。\n具体原因：{exc}",
        )
    return StartupTaskResult(
        success=True,
        title="开机自启已关闭",
        message="已删除注册表启动项、旧 VBS 和旧任务计划。",
    )
