import os
import platform
import subprocess
import sys
from dataclasses import dataclass


TASK_NAME = "SchoolDismissalSystem"
STARTUP_SCRIPT_NAME = "SchoolDismissalSystemStartup.vbs"


@dataclass
class StartupTaskResult:
    success: bool
    title: str
    message: str


def quote_powershell_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def quote_vbscript_string(value):
    return '"' + str(value).replace('"', '""') + '"'


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


def build_startup_vbs_script(executable_path, working_directory, arguments="", delay_milliseconds=30000):
    command = f'"{executable_path}"'
    if arguments:
        command += f' "{arguments}"'

    return "\n".join(
        [
            'Set WshShell = CreateObject("WScript.Shell")',
            f"WScript.Sleep {delay_milliseconds}",
            f"WshShell.CurrentDirectory = {quote_vbscript_string(working_directory)}",
            f"WshShell.Run {quote_vbscript_string(command)}, 1, False",
        ]
    )


def enable_startup_folder_fallback(executable_path, arguments, working_directory):
    startup_folder = get_user_startup_folder()
    if not startup_folder:
        return StartupTaskResult(
            success=False,
            title="开机自启设置失败",
            message="Windows 未返回当前用户的 Startup 文件夹位置。",
        )

    try:
        os.makedirs(startup_folder, exist_ok=True)
        script_path = os.path.join(startup_folder, STARTUP_SCRIPT_NAME)
        script = build_startup_vbs_script(
            executable_path=executable_path,
            arguments=arguments,
            working_directory=working_directory,
        )
        with open(script_path, "w", encoding="utf-8") as file:
            file.write(script)
    except Exception as exc:
        return StartupTaskResult(
            success=False,
            title="开机自启设置失败",
            message=f"任务计划无权限，Startup 启动脚本也创建失败：{exc}",
        )

    return StartupTaskResult(
        success=True,
        title="开机自启已启用",
        message=(
            "当前账号无权写入任务计划，已自动改用用户 Startup 启动脚本。\n"
            "登录后延迟 30 秒启动本系统，并自动设置正确起始目录。\n"
            f"启动脚本：{script_path}\n"
            f"程序路径：{executable_path}\n"
            f"起始目录：{working_directory}"
        ),
    )


def build_register_startup_task_script(task_name, executable_path, working_directory, arguments=""):
    command = [
        "$ErrorActionPreference = 'Stop'",
        f"$Action = New-ScheduledTaskAction -Execute {quote_powershell_string(executable_path)}"
        + (f" -Argument {quote_powershell_string(arguments)}" if arguments else "")
        + f" -WorkingDirectory {quote_powershell_string(working_directory)}",
        "$Trigger = New-ScheduledTaskTrigger -AtLogOn",
        "$Trigger.Delay = 'PT30S'",
        "$Settings = New-ScheduledTaskSettingsSet "
        "-StartWhenAvailable "
        "-MultipleInstances IgnoreNew "
        "-RestartCount 3 "
        "-RestartInterval (New-TimeSpan -Minutes 1)",
        "Register-ScheduledTask "
        f"-TaskName {quote_powershell_string(task_name)} "
        "-Action $Action "
        "-Trigger $Trigger "
        "-Settings $Settings "
        "-Description '校园放学语音播报系统开机自启' "
        "-Force | Out-Null",
    ]
    return "\n".join(command)


def enable_startup_task(task_name=TASK_NAME):
    if platform.system() != "Windows":
        return StartupTaskResult(
            success=False,
            title="当前系统不支持",
            message="一键开机自启只支持 Windows 客户端。",
        )

    executable_path, arguments, working_directory = get_startup_target()
    if not os.path.exists(executable_path):
        return StartupTaskResult(
            success=False,
            title="未找到程序文件",
            message=f"找不到要自启的程序：{executable_path}",
        )

    script = build_register_startup_task_script(
        task_name=task_name,
        executable_path=executable_path,
        arguments=arguments,
        working_directory=working_directory,
    )

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return StartupTaskResult(
            success=False,
            title="开机自启设置失败",
            message=str(exc),
        )

    if completed.returncode != 0:
        fallback_result = enable_startup_folder_fallback(
            executable_path=executable_path,
            arguments=arguments,
            working_directory=working_directory,
        )
        if fallback_result.success:
            return fallback_result

        detail = (completed.stderr or completed.stdout or "").strip()
        fallback_result.message = (
            "任务计划程序失败："
            + (detail or "没有输出具体原因。")
            + "\n"
            + fallback_result.message
        )
        return fallback_result

    return StartupTaskResult(
        success=True,
        title="开机自启已启用",
        message=(
            "已创建 Windows 任务计划：登录后延迟 30 秒启动本系统。\n"
            f"程序路径：{executable_path}\n"
            f"起始目录：{working_directory}"
        ),
    )
