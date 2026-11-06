import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QScrollArea
from src.ui.settings_dialog import SettingsDialog
from tests.test_settings_preview import FakeConfig, FakeLedService


def make_dialog():
    app = QApplication.instance() or QApplication([])
    service = FakeLedService(grades=['七年级', '八年级'])
    service.get_available_admin_classes = lambda school: [
        dict(class_id=f'{g}-{i}', grade_name=g, class_name=f'{i}班')
        for g in ['七年级', '八年级'] for i in range(1, 15)]
    widget = SettingsDialog(FakeConfig(), led_service=service)
    return app, widget


def test_basic_settings_merge_school_voice_and_advanced_without_losing_controls():
    app, widget = make_dialog()
    try:
        assert [widget.navigation.item(i).text() for i in range(widget.navigation.count())] == [
            '基础设置', '读卡设备', '屏幕展示']
        basic = widget.pages.widget(0)
        assert basic.isAncestorOf(widget.school_id_edit)
        assert basic.isAncestorOf(widget.tts_repeat_count_spin)
        assert basic.isAncestorOf(widget.api_base_url_edit)
        assert not widget.advanced_section.isExpanded()
        widget.advanced_section.toggle.click()
        assert widget.advanced_section.isExpanded()
        widget.tts_repeat_count_spin.setValue(5)
        widget.mqtt_enabled_check.setChecked(False)
        with patch('src.ui.settings_dialog.QMessageBox.information'):
            widget.save_settings()
        assert widget.config.get('tts_repeat_count') == 5
        assert widget.config.get('mqtt_enabled') is False
    finally:
        widget.close()


def test_search_and_bulk_selection_are_scoped_to_current_grade_and_results():
    app, widget = make_dialog()
    try:
        editor = widget.class_selector
        editor.select_grade('七年级')
        editor.search.setText('14班')
        editor.clear_button.click()
        assert widget._current_led_class_filter() == {'七年级': [f'七年级-{i}' for i in range(1, 14)]}
        editor.select_all_button.click()
        assert len(widget._current_led_class_filter()['七年级']) == 14
        assert '八年级' not in widget._current_led_class_filter()
        widget.led_all_classes_checks['七年级'].setChecked(True)
        editor.search.clear()
        widget.led_class_checks['七年级']['七年级-3'].click()
        assert len(widget._current_led_class_filter()['七年级']) == 13
        editor.select_grade('八年级')
        assert editor.search.text() == ''
        assert not widget.led_class_groups['七年级'].isVisible()
        assert widget.led_all_classes_checks['八年级'].isChecked()
        editor.search.setText('没有这个班')
        assert not editor.select_all_button.isEnabled()
        assert not editor.clear_button.isEnabled()
    finally:
        widget.close()


def test_screen_context_and_preview_do_not_scroll_away_with_form():
    app, widget = make_dialog()
    try:
        widget.navigation.setCurrentRow(2)
        widget.show()
        app.processEvents()
        ancestor = widget.led_tabs.parentWidget()
        while ancestor is not None and ancestor is not widget.pages.widget(2):
            assert not isinstance(ancestor, QScrollArea)
            ancestor = ancestor.parentWidget()
        for control in (widget.screen_panel, widget.preview_generate_btn, widget.save_btn):
            assert control.isVisible()
        assert widget.led_tabs.count() == 4
        assert widget.led_tabs.tabText(0) == '显示范围'
        widget.led_tabs.setCurrentIndex(3)
        app.processEvents()
        assert widget.led_ip_edit.isVisible()
        assert widget.screen_panel.name_edit.isVisible()
        widget.resize(1040, 700)
        app.processEvents()
        # At the smallest supported size the preview cannot overlap its status or tools.
        assert widget.preview_status_label.y() >= widget.preview_scroll.geometry().bottom()
        assert widget.preview_prev_btn.y() >= widget.preview_actual_font_label.geometry().bottom()
        assert all(area.horizontalScrollBar().maximum() == 0
                   for area in widget.led_tabs.findChildren(QScrollArea))
    finally:
        widget.close()
        app.processEvents()


def test_range_validation_returns_to_screen_workspace():
    app, widget = make_dialog()
    try:
        widget.led_all_classes_checks['七年级'].setChecked(False)
        for checkbox in widget.led_class_checks['七年级'].values():
            checkbox.setChecked(False)
        widget.navigation.setCurrentRow(0)
        with patch('src.ui.settings_dialog.QMessageBox.warning'):
            widget.save_settings()
        assert widget.navigation.currentRow() == 2
        assert widget.config.get('led_screens') is None
    finally:
        widget.close()
