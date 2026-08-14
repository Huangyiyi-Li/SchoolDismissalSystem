import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_exe
from src.app_info import WINDOWS_EXE_NAME, WINDOWS_ZIP_NAME


class BuildExeLedTests(unittest.TestCase):
    def test_tag_release_does_not_duplicate_files_as_actions_artifact(self):
        workflow = Path(".github/workflows/windows-build.yml").read_text(
            encoding="utf-8"
        )
        upload_step = workflow.split("- name: Upload Windows build", 1)[1].split(
            "- name: Publish GitHub pre-release", 1
        )[0]

        self.assertIn("!startsWith(github.ref, 'refs/tags/')", upload_step)
        self.assertIn("retention-days: 3", upload_step)

    def test_release_zip_contains_led_bridge_sdk_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dist = root / "dist"
            bridge = root / "led-bridge"
            (bridge / "lib").mkdir(parents=True)
            (bridge / "runtime" / "bin").mkdir(parents=True)
            dist.mkdir()
            (dist / WINDOWS_EXE_NAME).write_bytes(b"exe")
            (bridge / "led-bridge.jar").write_bytes(b"bridge")
            (bridge / "README.md").write_text("bridge", encoding="utf-8")
            for name in build_exe.LED_BRIDGE_REQUIRED_JARS:
                (bridge / "lib" / name).write_bytes(b"sdk")
            (bridge / "runtime" / "bin" / "java.exe").write_bytes(b"java")

            with patch.object(build_exe, "DIST_DIR", dist), patch.object(
                build_exe, "LED_BRIDGE_DIR", bridge
            ):
                build_exe.create_release_files()

            with zipfile.ZipFile(dist / WINDOWS_ZIP_NAME) as archive:
                names = set(archive.namelist())
            self.assertIn("led-bridge/led-bridge.jar", names)
            self.assertIn("led-bridge/lib/bx06-0.6.5-SNAPSHOT.jar", names)
            self.assertIn("led-bridge/runtime/bin/java.exe", names)

    def test_release_fails_when_bundled_java_runtime_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dist = root / "dist"
            bridge = root / "led-bridge"
            (bridge / "lib").mkdir(parents=True)
            dist.mkdir()
            (dist / WINDOWS_EXE_NAME).write_bytes(b"exe")
            (bridge / "led-bridge.jar").write_bytes(b"bridge")
            (bridge / "README.md").write_text("bridge", encoding="utf-8")
            for name in build_exe.LED_BRIDGE_REQUIRED_JARS:
                (bridge / "lib" / name).write_bytes(b"sdk")

            with patch.object(build_exe, "DIST_DIR", dist), patch.object(
                build_exe, "LED_BRIDGE_DIR", bridge
            ):
                with self.assertRaisesRegex(FileNotFoundError, "runtime"):
                    build_exe.create_release_files()

    def test_release_fails_when_one_official_sdk_dependency_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dist = root / "dist"
            bridge = root / "led-bridge"
            (bridge / "lib").mkdir(parents=True)
            (bridge / "runtime" / "bin").mkdir(parents=True)
            dist.mkdir()
            (dist / WINDOWS_EXE_NAME).write_bytes(b"exe")
            (bridge / "led-bridge.jar").write_bytes(b"bridge")
            (bridge / "README.md").write_text("bridge", encoding="utf-8")
            missing = "uia-utils-0.3.1.jar"
            for name in build_exe.LED_BRIDGE_REQUIRED_JARS - {missing}:
                (bridge / "lib" / name).write_bytes(b"sdk")
            (bridge / "runtime" / "bin" / "java.exe").write_bytes(b"java")

            with patch.object(build_exe, "DIST_DIR", dist), patch.object(
                build_exe, "LED_BRIDGE_DIR", bridge
            ):
                with self.assertRaisesRegex(FileNotFoundError, missing):
                    build_exe.create_release_files()


if __name__ == "__main__":
    unittest.main()
