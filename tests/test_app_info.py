import unittest

from src.app_info import (
    APP_NAME,
    APP_VERSION,
    APP_VERSION_LABEL,
    WINDOWS_EXE_NAME,
    WINDOWS_SHA256_NAME,
    WINDOWS_ZIP_NAME,
)


class AppInfoTests(unittest.TestCase):
    def test_product_and_build_names_share_single_version(self):
        self.assertEqual(APP_NAME, "数智家校放学系统")
        self.assertEqual(APP_VERSION, "2.1.0-beta.3")
        self.assertEqual(APP_VERSION_LABEL, "版本 v2.1.0-beta.3")
        self.assertEqual(WINDOWS_EXE_NAME, "数智家校放学系统.exe")
        self.assertEqual(
            WINDOWS_ZIP_NAME,
            "数智家校放学系统-v2.1.0-beta.3-windows-x64.zip",
        )
        self.assertEqual(
            WINDOWS_SHA256_NAME,
            "数智家校放学系统-v2.1.0-beta.3-windows-x64.zip.sha256",
        )


if __name__ == "__main__":
    unittest.main()
