import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

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
    def __init__(self, grades=None):
        self.preview_calls = []
        self.grades = grades or ["一年级", "二年级", "三年级"]

    def get_available_admin_grades(self, school_id=None):
        return list(self.grades)

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
        self.assertEqual(kwargs["title_font_size"], 0)
        self.assertEqual(kwargs["header_font_size"], 0)
        self.assertEqual(kwargs["cell_font_size"], 0)
        self.assertEqual(kwargs['title_scale_percent'], 100)
        self.assertEqual(kwargs['table_scale_percent'], 100)

    def test_all_grades_is_safe_default_and_disables_individual_choices(self):
        dialog, _service = self.make_dialog()

        self.assertTrue(dialog.led_all_grades_check.isChecked())
        self.assertEqual(
            list(dialog.led_grade_checks),
            ["一年级", "二年级", "三年级"],
        )
        self.assertTrue(
            all(not checkbox.isEnabled() for checkbox in dialog.led_grade_checks.values())
        )

    def test_selected_grades_are_saved_and_forwarded_to_preview(self):
        dialog, service = self.make_dialog()
        dialog.led_all_grades_check.setChecked(False)
        dialog.led_grade_checks["一年级"].setChecked(False)
        dialog.led_grade_checks["二年级"].setChecked(True)
        dialog.led_grade_checks["三年级"].setChecked(False)

        dialog.preview_generate_btn.click()

        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        self.assertTrue(self.wait_until(lambda: dialog.preview_generate_btn.isEnabled()))
        kwargs = service.preview_calls[0][1]
        self.assertEqual(kwargs["grade_filter_mode"], "selected")
        self.assertEqual(kwargs["visible_grades"], ["二年级"])
        self.assertIn("LED 年级 二年级", dialog.preview_status_label.text())

        with patch("src.ui.settings_dialog.QMessageBox.information"):
            dialog.save_settings()

        self.assertEqual(dialog.config.values["led_grade_filter_mode"], "selected")
        self.assertEqual(dialog.config.values["led_visible_grades"], ["二年级"])

    def test_saved_grade_missing_from_current_sync_is_marked_invalid(self):
        config = FakeConfig()
        config.values.update(
            {
                "led_grade_filter_mode": "selected",
                "led_visible_grades": ["七年级"],
            }
        )
        dialog = SettingsDialog(
            config,
            led_service=FakeLedService(grades=["一年级", "二年级"]),
        )
        self.addCleanup(dialog.close)

        self.assertIn("已失效", dialog.led_grade_checks["七年级"].text())

    def test_zero_font_size_is_presented_as_automatic(self):
        config = FakeConfig()
        config.values.update({
            "led_title_font_size": 0,
            "led_header_font_size": 0,
            "led_cell_font_size": 0,
        })
        dialog = SettingsDialog(config, led_service=FakeLedService())
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.led_title_scale_slider.value(), 100)
        self.assertEqual(dialog.led_table_scale_slider.value(), 100)
        self.assertIn("自动适配", dialog.led_font_size_hint.text())

    def test_dual_color_selection_updates_guidance_and_preview_request(self):
        dialog, service = self.make_dialog()
        dialog.led_color_mode_combo.setCurrentIndex(
            dialog.led_color_mode_combo.findData("double")
        )

        self.assertIn("双色状态的文字和颜色", dialog.led_color_hint.text())
        self.assertIn("256K", dialog.led_size_hint.text())
        dialog.preview_generate_btn.click()

        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        self.assertEqual(service.preview_calls[0][1]["color_mode"], "double")

    def test_custom_grade_pages_and_state_styles_are_forwarded_to_preview(self):
        dialog, service = self.make_dialog()
        dialog.led_grade_pages_edit.setPlainText('一年级、二年级\n三年级')
        dialog.led_status_edits['未放学'].setText('')
        dialog.led_status_edits['放学中'].setText('○')
        dialog.led_status_edits['已放学'].setText('●')
        combo = dialog.led_status_color_combos['已放学']
        combo.setCurrentIndex(combo.findData('yellow'))
        dialog.preview_generate_btn.click()
        self.assertTrue(self.wait_until(lambda: len(service.preview_calls) == 1))
        kwargs = service.preview_calls[0][1]
        self.assertEqual(kwargs['grade_pages'], [['一年级', '二年级'], ['三年级']])
        self.assertEqual(kwargs['status_labels']['已放学'], '●')
        self.assertEqual(kwargs['status_colors']['已放学'], 'yellow')

    def test_small_led_preview_displays_legibility_warning(self):
        dialog, _service = self.make_dialog()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preview.bmp'
            Image.new('1', (192, 96), 0).save(path)
            dialog._preview_pages = [path]
            dialog._preview_metrics = [{
                'kind': 'admin', 'title_px': 10, 'header_px': 6, 'cell_px': 6,
                'row_count': 6, 'column_count': 6, 'max_status_chars': 3,
            }]
            dialog._preview_source_width = 192
            dialog._preview_source_height = 96
            dialog._preview_color_mode = 'single'
            dialog._show_preview_page()
            self.assertIn('6 px', dialog.preview_readability_label.text())
            self.assertIn('空心/实心圆', dialog.preview_readability_label.text())


if __name__ == "__main__":
    unittest.main()
