import os
import time
import unittest
from unittest.mock import patch

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
            "led_color_mode": "single",
            "led_page_seconds": 5,
            "led_grades_per_page": 2,
            "led_layout_regions": 1,
            "led_club_rows_per_group": 4,
            "led_club_groups_per_page": 5,
            "led_dismissed_delay_seconds": 5,
            "led_show_title": True,
            "led_school_title": "数智家校\n放学系统",
            "led_title_font_size": 26,
            "led_header_font_size": 18,
            "led_cell_font_size": 14,
            "tts_rate": 160,
            "tts_repeat_count": 2,
            "tts_repeat_interval_seconds": 0.6,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        pass


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

    def test_voice_playback_settings_are_loaded(self):
        dialog, _service = self.make_dialog()

        self.assertFalse(dialog.tts_default_rate_check.isChecked())
        self.assertEqual(dialog.tts_rate_spin.value(), 160)
        self.assertEqual(dialog.tts_repeat_count_spin.value(), 2)
        self.assertAlmostEqual(dialog.tts_repeat_interval_spin.value(), 0.6)

    def test_invalid_voice_settings_fall_back_without_blocking_settings_dialog(self):
        config = FakeConfig()
        config.values.update({
            "tts_rate": "bad",
            "tts_repeat_count": "bad",
            "tts_repeat_interval_seconds": "bad",
        })

        dialog = SettingsDialog(config, led_service=FakeLedService())
        self.addCleanup(dialog.close)

        self.assertTrue(dialog.tts_default_rate_check.isChecked())
        self.assertEqual(dialog.tts_repeat_count_spin.value(), 3)
        self.assertEqual(dialog.tts_repeat_interval_spin.value(), 0)

    def test_voice_playback_settings_are_saved(self):
        dialog, _service = self.make_dialog()
        dialog.tts_default_rate_check.setChecked(False)
        dialog.tts_rate_spin.setValue(180)
        dialog.tts_repeat_count_spin.setValue(4)
        dialog.tts_repeat_interval_spin.setValue(1.2)

        with patch("src.ui.settings_dialog.QMessageBox.information"):
            dialog.save_settings()

        self.assertEqual(dialog.config.values["tts_rate"], 180)
        self.assertEqual(dialog.config.values["tts_repeat_count"], 4)
        self.assertEqual(
            dialog.config.values["tts_repeat_interval_seconds"], 1.2
        )

    def test_generate_preview_button_runs_current_values_in_background(self):
        dialog, service = self.make_dialog()

        dialog.preview_generate_btn.click()

        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        self.assertTrue(self.wait_until(lambda: dialog.preview_generate_btn.isEnabled()))
        kwargs = service.preview_calls[0][1]
        self.assertEqual(kwargs["club_rows_per_group"], 4)
        self.assertEqual(kwargs["club_groups_per_page"], 5)
        self.assertEqual(kwargs["color_mode"], "single")
        self.assertEqual(kwargs["title_font_size"], 26)
        self.assertEqual(kwargs["header_font_size"], 18)
        self.assertEqual(kwargs["cell_font_size"], 14)

    def test_zero_font_size_is_presented_as_automatic(self):
        config = FakeConfig()
        config.values.update({
            "led_title_font_size": 0,
            "led_header_font_size": 0,
            "led_cell_font_size": 0,
        })
        dialog = SettingsDialog(config, led_service=FakeLedService())
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.led_title_font_size_spin.value(), 0)
        self.assertEqual(dialog.led_title_font_size_spin.text(), "自动")
        self.assertIn("放不下时自动缩小", dialog.led_font_size_hint.text())

    def test_dual_color_selection_updates_guidance_and_preview_request(self):
        dialog, service = self.make_dialog()
        dialog.led_color_mode_combo.setCurrentIndex(
            dialog.led_color_mode_combo.findData("double")
        )

        self.assertIn("未放学=黄", dialog.led_color_hint.text())
        self.assertIn("256K", dialog.led_size_hint.text())
        dialog.preview_generate_btn.click()

        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        self.assertEqual(service.preview_calls[0][1]["color_mode"], "double")


if __name__ == "__main__":
    unittest.main()
