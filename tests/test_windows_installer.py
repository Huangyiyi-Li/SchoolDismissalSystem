import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WindowsInstallerTests(unittest.TestCase):
    def test_installer_uses_stable_per_user_location_and_bundles_led_bridge(self):
        installer_path = PROJECT_ROOT / "installer" / "windows-installer.iss"

        self.assertTrue(installer_path.exists(), "缺少 Windows 安装器脚本")
        content = installer_path.read_text(encoding="utf-8")
        self.assertIn(
            r"DefaultDirName={localappdata}\Programs\数智家校放学系统",
            content,
        )
        self.assertIn("PrivilegesRequired=lowest", content)
        self.assertIn(r'Source: "..\dist\数智家校放学系统.exe"', content)
        self.assertIn(r'Source: "..\led-bridge\*"', content)
        self.assertIn("procedure CurStepChanged(CurStep: TSetupStep);", content)
        self.assertIn("CurStep = ssPostInstall", content)

    def test_windows_workflow_builds_and_publishes_setup_asset(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "windows-build.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("WINDOWS_SETUP_NAME", workflow)
        self.assertIn("ISCC.exe", workflow)
        self.assertIn("setup_name", workflow)


if __name__ == "__main__":
    unittest.main()
