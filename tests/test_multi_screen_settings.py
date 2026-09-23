import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from src.ui.settings_dialog import SettingsDialog
from tests.test_settings_preview import FakeConfig, FakeLedService


def dialog():
    app = QApplication.instance() or QApplication([])
    widget = SettingsDialog(FakeConfig(), led_service=FakeLedService())
    return app, widget


def test_add_screen_save_reload_and_cancel_isolated():
    app, widget = dialog()
    try:
        panel = getattr(widget, 'screen_panel', None)
        assert panel is not None, 'settings need a multi-screen editor'
        panel.add_screen()
        widget.led_ip_edit.setText('192.168.100.2')
        panel.name_edit.setText('北门屏')
        widget.led_all_grades_check.setChecked(False)
        widget.led_grade_checks['三年级'].setChecked(True)
        assert widget.config.get('led_screens') is None
        with patch('src.ui.settings_dialog.QMessageBox.information'):
            widget.save_settings()
        screens = widget.config.get('led_screens')
        assert len(screens) == 2
        assert screens[1]['name'] == '北门屏'
        reopened = SettingsDialog(widget.config, led_service=FakeLedService())
        try:
            reopened.screen_panel.screen_list.setCurrentRow(1)
            assert reopened.led_ip_edit.text() == '192.168.100.2'
            assert reopened.led_grade_checks['三年级'].isChecked()
            reopened.led_ip_edit.setText('192.168.100.9')
            reopened.reject()
            assert widget.config.get('led_screens')[1]['settings']['led_controller_ip'] == '192.168.100.2'
        finally:
            reopened.close()
    finally:
        widget.close()


def test_shared_plan_edits_propagate_and_can_be_detached():
    app, widget = dialog()
    try:
        panel = getattr(widget, 'screen_panel', None)
        assert panel is not None
        panel.add_screen()
        panel.plan_combo.setCurrentIndex(0)
        widget.led_title_edit.setPlainText('共同标题')
        panel.screen_list.setCurrentRow(0)
        assert widget.led_title_edit.toPlainText() == '共同标题'
        panel.detach_plan()
        widget.led_title_edit.setPlainText('独立标题')
        panel.screen_list.setCurrentRow(1)
        assert widget.led_title_edit.toPlainText() == '共同标题'
    finally:
        widget.close()


def test_duplicate_controller_blocks_save_without_mutating_config():
    app, widget = dialog()
    try:
        panel = getattr(widget, 'screen_panel', None)
        assert panel is not None
        panel.add_screen()
        widget.led_ip_edit.setText('192.168.100.1')
        with patch('src.ui.settings_dialog.QMessageBox.warning') as warning:
            widget.save_settings()
        assert warning.called
        assert widget.config.get('led_screens') is None
    finally:
        widget.close()


def test_missing_grade_in_another_plan_is_preserved_on_open():
    app, widget = dialog()
    try:
        panel = widget.screen_panel
        panel.add_screen()
        setup = panel.values()
        setup[0][1]['settings'].update(led_grade_filter_mode='selected', led_visible_grades=['六年级'])
        config = FakeConfig()
        config.values.update(led_screens=setup[0], led_display_plans=setup[1])
        second = SettingsDialog(config, led_service=FakeLedService())
        try:
            second.screen_panel.screen_list.setCurrentRow(1)
            assert '六年级' in second.led_grade_checks
            assert second.led_grade_checks['六年级'].isChecked()
        finally:
            second.close()
    finally:
        widget.close()


def test_each_screen_keeps_its_own_rotation_pages():
    app, widget = dialog()
    try:
        panel = widget.screen_panel
        widget.led_grade_pages_edit.setPlainText('一年级、二年级\n三年级')
        panel.add_screen()
        widget.led_grade_pages_edit.setPlainText('一年级\n二年级、三年级')
        assert panel.store_form()
        panel.screen_list.setCurrentRow(0)
        assert widget.led_grade_pages_edit.toPlainText() == '一年级、二年级\n三年级'
        panel.screen_list.setCurrentRow(1)
        assert widget.led_grade_pages_edit.toPlainText() == '一年级\n二年级、三年级'
    finally:
        widget.close()


def test_switching_screen_clears_previous_screen_preview():
    app, widget = dialog()
    try:
        widget.screen_panel.add_screen()
        widget._preview_pages = ['old-screen.bmp']
        widget._preview_state.has_preview = True
        widget.screen_panel.screen_list.setCurrentRow(0)
        assert widget._preview_pages == []
        assert not widget._preview_state.has_preview
    finally:
        widget.close()
