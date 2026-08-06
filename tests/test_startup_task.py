import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services import startup_task


class FakeRegistryKey:
    def __init__(self, registry, path, access=None):
        self.registry = registry
        self.path = path
        self.access = access

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        self.values = {}

    def CreateKey(self, _root, path):
        return FakeRegistryKey(self, path)

    def OpenKey(self, _root, path, _reserved=0, access=None):
        return FakeRegistryKey(self, path, access=access)

    def SetValueEx(self, key, name, _reserved, _kind, value):
        self.values[(key.path, name)] = value

    def QueryValueEx(self, key, name):
        try:
            return self.values[(key.path, name)], self.REG_SZ
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def DeleteValue(self, key, name):
        if key.access != self.KEY_SET_VALUE:
            raise PermissionError("registry key was not opened for writing")
        try:
            del self.values[(key.path, name)]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc


class StartupTaskTests(unittest.TestCase):
    def test_enable_uses_current_user_registry_and_removes_legacy_vbs(self):
        registry = FakeWinreg()
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "数智家校放学系统"
            app_dir.mkdir()
            executable = app_dir / "数智家校放学系统.exe"
            executable.touch()
            startup_dir = (
                Path(tmpdir)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "Startup"
            )
            startup_dir.mkdir(parents=True)
            legacy_vbs = startup_dir / startup_task.STARTUP_SCRIPT_NAME
            legacy_vbs.write_text("old", encoding="utf-8")
            task_missing = subprocess.CompletedProcess(
                [],
                1,
                stdout="",
                stderr="ERROR: The system cannot find the file specified.",
            )

            with patch.dict(os.environ, {"APPDATA": tmpdir}), \
                 patch.dict(sys.modules, {"winreg": registry}), \
                 patch.object(startup_task.platform, "system", return_value="Windows"), \
                 patch.object(
                     startup_task,
                     "get_startup_target",
                     return_value=(str(executable), "", str(app_dir)),
                 ), \
                 patch.object(startup_task.subprocess, "run", return_value=task_missing):
                result = startup_task.enable_startup_task()

            registry_key = (
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                startup_task.TASK_NAME,
            )
            self.assertTrue(result.success, result.message)
            self.assertEqual(registry.values[registry_key], f'"{executable}"')
            self.assertFalse(legacy_vbs.exists())
            self.assertIn("注册表", result.message)

    def test_disable_removes_registry_value_and_legacy_vbs(self):
        disable = getattr(startup_task, "disable_startup_task", None)
        self.assertTrue(callable(disable), "缺少关闭开机自启能力")
        registry = FakeWinreg()
        registry_key = (
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            startup_task.TASK_NAME,
        )
        registry.values[registry_key] = r'"D:\App\数智家校放学系统.exe"'

        with tempfile.TemporaryDirectory() as tmpdir:
            startup_dir = (
                Path(tmpdir)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "Startup"
            )
            startup_dir.mkdir(parents=True)
            legacy_vbs = startup_dir / startup_task.STARTUP_SCRIPT_NAME
            legacy_vbs.write_text("old", encoding="utf-8")
            task_missing = subprocess.CompletedProcess([], 1, stdout="", stderr="找不到指定的文件")

            with patch.dict(os.environ, {"APPDATA": tmpdir}), \
                 patch.dict(sys.modules, {"winreg": registry}), \
                 patch.object(startup_task.platform, "system", return_value="Windows"), \
                 patch.object(startup_task.subprocess, "run", return_value=task_missing):
                result = disable()

            self.assertTrue(result.success, result.message)
            self.assertNotIn(registry_key, registry.values)
            self.assertFalse(legacy_vbs.exists())

    def test_status_distinguishes_enabled_stale_and_disabled_targets(self):
        get_status = getattr(startup_task, "get_startup_status", None)
        self.assertTrue(callable(get_status), "缺少开机自启状态识别能力")
        registry = FakeWinreg()
        registry_key = (
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            startup_task.TASK_NAME,
        )
        current_target = r"D:\App\数智家校放学系统.exe"

        with patch.dict(sys.modules, {"winreg": registry}), \
             patch.object(startup_task.platform, "system", return_value="Windows"), \
             patch.object(
                 startup_task,
                 "get_startup_target",
                 return_value=(current_target, "", r"D:\App"),
             ):
            self.assertEqual(get_status(), "disabled")
            registry.values[registry_key] = f'"{current_target}"'
            self.assertEqual(get_status(), "enabled")
            registry.values[registry_key] = r'"D:\Old\数智家校放学系统.exe"'
            self.assertEqual(get_status(), "repair")

    def test_toolbar_label_explains_enable_disable_and_repair_actions(self):
        label_for = getattr(startup_task, "startup_action_label", None)
        self.assertTrue(callable(label_for), "缺少开机自启操作文案映射")

        self.assertEqual(label_for("disabled"), "启用开机自启")
        self.assertEqual(label_for("enabled"), "关闭开机自启")
        self.assertEqual(label_for("repair"), "修复开机自启")

    def test_legacy_cleanup_failure_is_not_misreported_as_registry_failure(self):
        with patch.object(startup_task.platform, "system", return_value="Windows"), \
             patch.object(
                 startup_task,
                 "get_startup_target",
                 return_value=(__file__, "", str(Path(__file__).parent)),
             ), \
             patch.object(
                 startup_task,
                 "_cleanup_legacy_startup_entries",
                 side_effect=PermissionError("旧任务计划拒绝访问"),
             ):
            result = startup_task.enable_startup_task()

        self.assertFalse(result.success)
        self.assertIn("清理旧版开机启动项失败", result.message)
        self.assertIn("旧任务计划拒绝访问", result.message)


if __name__ == "__main__":
    unittest.main()
