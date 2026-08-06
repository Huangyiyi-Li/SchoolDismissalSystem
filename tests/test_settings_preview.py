import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from src.ui.settings_dialog import SettingsDialog
except ModuleNotFoundError:
    QTest = None
    QApplication = None
    SettingsDialog = None


class FakeConfig:
    def __init__(self):
        self.values = {
            "school_id": "40125",
            "led_controller_ip": "192.168.100.1",
            "led_controller_port": 5005,
            "led_width": 1024,
            "led_height": 96,
            "led_page_seconds": 5,
            "led_grades_per_page": 2,
            "led_layout_regions": 1,
            "led_club_rows_per_group": 4,
            "led_club_groups_per_page": 5,
            "led_dismissed_delay_seconds": 5,
            "led_show_title": True,
            "led_school_title": "数智家校\n放学系统",
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeLedService:
    def __init__(self):
        self.preview_calls = []

    def render_preview_pages(self, *args, **kwargs):
        self.preview_calls.append((args, kwargs))
        return []


@unittest.skipIf(QApplication is None, "PyQt6 is not installed in this test environment")
class SettingsPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self):
        service = FakeLedService()
        dialog = SettingsDialog(FakeConfig(), led_service=service)
        self.addCleanup(dialog.close)
        return dialog, service

    def wait_until(self, predicate, timeout_ms=1000):
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return True
            QTest.qWait(10)
        return predicate()

    def test_opening_and_editing_settings_do_not_auto_generate_preview(self):
        dialog, service = self.make_dialog()

        dialog.led_width_edit.setText("1000")
        QTest.qWait(350)
        QApplication.processEvents()

        self.assertEqual(service.preview_calls, [])
        self.assertEqual(dialog.preview_generate_btn.text(), "生成预览")

    def test_generate_preview_button_runs_current_values_in_background(self):
        dialog, service = self.make_dialog()

        dialog.preview_generate_btn.click()

        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        self.assertTrue(self.wait_until(lambda: dialog.preview_generate_btn.isEnabled()))
        kwargs = service.preview_calls[0][1]
        self.assertEqual(kwargs["club_rows_per_group"], 4)
        self.assertEqual(kwargs["club_groups_per_page"], 5)


if __name__ == "__main__":
    unittest.main()
