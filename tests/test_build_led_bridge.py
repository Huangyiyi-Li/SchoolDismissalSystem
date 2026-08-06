import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_led_bridge import build_bridge


class BuildLedBridgeTests(unittest.TestCase):
    def test_bridge_validates_requested_color_mode_against_controller_profile(self):
        source = Path(
            "led-bridge/src/cn/xxt/dismissal/led/OnbonLedBridge.java"
        ).read_text(encoding="utf-8")

        self.assertIn('"--color"', source)
        self.assertIn("ScreenColorType.DOUBLE", source)
        self.assertIn("屏幕颜色配置不一致", source)

    def make_layout(self, root):
        bridge = root / "led-bridge"
        (bridge / "src" / "example").mkdir(parents=True)
        (bridge / "lib").mkdir()
        (bridge / "src" / "example" / "Bridge.java").write_text(
            "package example; public class Bridge {}",
            encoding="utf-8",
        )
        java_home = root / "jdk"
        (java_home / "bin").mkdir(parents=True)
        suffix = ".exe" if os.name == "nt" else ""
        (java_home / "bin" / f"javac{suffix}").write_bytes(b"tool")
        (java_home / "bin" / f"jar{suffix}").write_bytes(b"tool")
        return bridge, java_home

    def test_build_invokes_javac_and_jar_and_requires_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge, java_home = self.make_layout(root)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if Path(command[0]).stem == "jar":
                    (bridge / "led-bridge.jar").write_bytes(b"jar")
                return subprocess.CompletedProcess(command, 0)

            output = build_bridge(
                bridge_dir=bridge,
                java_home=java_home,
                runner=runner,
            )

            self.assertEqual(output, (bridge / "led-bridge.jar").resolve())
            self.assertEqual(len(calls), 2)
            self.assertIn("-source", calls[0][0])
            self.assertEqual(calls[0][1]["check"], True)

    def test_compile_failure_stops_before_packaging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge, java_home = self.make_layout(root)
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                raise subprocess.CalledProcessError(1, command)

            with self.assertRaises(subprocess.CalledProcessError):
                build_bridge(
                    bridge_dir=bridge,
                    java_home=java_home,
                    runner=runner,
                )

            self.assertEqual(len(calls), 1)
            self.assertFalse((bridge / "led-bridge.jar").exists())

    def test_uses_jdk_tools_from_path_when_java_home_is_unset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge, java_home = self.make_layout(root)
            suffix = ".exe" if os.name == "nt" else ""
            tools = {
                "javac": str(java_home / "bin" / f"javac{suffix}"),
                "jar": str(java_home / "bin" / f"jar{suffix}"),
            }

            def runner(command, **kwargs):
                if Path(command[0]).stem == "jar":
                    (bridge / "led-bridge.jar").write_bytes(b"jar")
                return subprocess.CompletedProcess(command, 0)

            with patch.dict(os.environ, {"JAVA_HOME": ""}), patch(
                "tools.build_led_bridge.shutil.which",
                side_effect=lambda name: tools.get(name),
            ):
                output = build_bridge(bridge_dir=bridge, runner=runner)

            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
