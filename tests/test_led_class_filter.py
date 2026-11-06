import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from src.database import DatabaseManager
from src.services.led_service import LedService
from src.services import led_renderer as renderer
from tests.test_led_service import FakeConfig, FakeBridge, FakeTimerFactory


def test_carousel_bitmap_has_no_footer_and_uses_full_table_height(tmp_path):
    classes = [dict(class_id=str(i), grade_name='七年级', class_name=f'{i}班')
               for i in range(1, 15)]
    with patch.object(renderer, '_draw_centered', wraps=renderer._draw_centered) as draw:
        paths = renderer.render_led_pages('', classes, {}, tmp_path, width=416, height=64,
                                          show_title=False, class_layout='carousel',
                                          classes_per_segment=7)
    assert len(paths) == 2
    assert not any('/2 ' in str(call.args[2]) for call in draw.call_args_list)
    grade_boxes = [call.args[1] for call in draw.call_args_list if call.args[2] == '七年级']
    assert all(box[3] == 64 for box in grade_boxes)


def test_selected_classes_reach_real_preview_live_and_test_output(tmp_path):
    cfg = FakeConfig({'school_id': 'demo', 'led_visible_classes_by_grade': {'七年级': ['b']}})
    db = DatabaseManager(str(tmp_path / 'demo.db'))
    for cid, grade, name in [('a', '七年级', '1班'), ('b', '七年级', '2班'),
                              ('c', '八年级', '1班')]:
        db.upsert_led_class('demo', 1, cid, grade, name)
    db.upsert_led_class('demo', 2, 'club', '', '社团')
    service = LedService(cfg, db, bridge=FakeBridge(), output_dir=tmp_path / 'live',
                         timer_factory=FakeTimerFactory(), submitter=lambda task: task())
    try:
        with patch.object(renderer, '_draw_centered', wraps=renderer._draw_centered) as draw:
            service.render_preview_pages(tmp_path / 'preview', 416, 96, 2, 1, False, '')
        labels = [call.args[2] for call in draw.call_args_list]
        assert '2班' in labels and '八年级' in labels
        # The first grade's omitted 1班 has no status cell; the other grade retains it.
        filtered = service._filter_classes_by_grades({1: db.get_led_classes('demo', 1),
                                                      2: db.get_led_classes('demo', 2)})
        assert [c['class_id'] for c in filtered[1]] == ['b', 'c']
        assert [c['class_id'] for c in filtered[2]] == ['club']
        assert not service._class_status_affects_led('a', 1)
        assert service._class_status_affects_led('b', 1)
        with patch('src.services.led_service.render_led_pages', wraps=renderer.render_led_pages) as render:
            service.refresh()
            assert [c['class_id'] for c in render.call_args.args[1]] == ['b', 'c']
            service.send_test_screen(visible_classes_by_grade={'七年级': ['a'], '八年级': []})
            assert [c['class_id'] for c in render.call_args.args[1]] == ['a']
        assert service.render_preview_pages(tmp_path / 'empty', 416, 96, 2, 1, False, '',
                   grade_filter_mode='selected', visible_grades=['七年级'],
                   visible_classes_by_grade={'七年级': []})  # Clubs still render.
    finally:
        service.shutdown()


def test_class_selection_is_independent_per_screen_and_survives_reopen():
    from PyQt6.QtWidgets import QApplication
    from src.ui.settings_dialog import SettingsDialog
    from tests.test_settings_preview import FakeConfig as SettingsConfig, FakeLedService
    app = QApplication.instance() or QApplication([])
    service = FakeLedService(grades=['七年级', '八年级'])
    service.get_available_admin_classes = lambda school_id: [
        dict(class_id=f'{g}-{i}', grade_name=g, class_name=f'{i}班')
        for g in ['七年级', '八年级'] for i in range(1, 4)]
    widget = SettingsDialog(SettingsConfig(), led_service=service)
    reopened = None
    try:
        widget.led_all_classes_checks['七年级'].setChecked(False)
        widget.led_class_checks['七年级']['七年级-1'].setChecked(False)
        assert widget._get_led_values(False)['visible_classes_by_grade'] == {'七年级': ['七年级-2', '七年级-3']}
        widget.screen_panel.add_screen()
        widget.led_all_classes_checks['七年级'].setChecked(True)
        widget.led_all_classes_checks['八年级'].setChecked(False)
        widget.led_class_checks['八年级']['八年级-2'].setChecked(False)
        widget.screen_panel.screen_list.setCurrentRow(0)
        assert not widget.led_class_checks['七年级']['七年级-1'].isChecked()
        assert widget.led_all_classes_checks['八年级'].isChecked()
        with patch('src.ui.settings_dialog.QMessageBox.information'):
            widget.save_settings()
        reopened = SettingsDialog(widget.config, led_service=service)
        assert reopened._get_led_values(False)['visible_classes_by_grade'] == {'七年级': ['七年级-2', '七年级-3']}
        reopened.screen_panel.screen_list.setCurrentRow(1)
        assert reopened._get_led_values(False)['visible_classes_by_grade'] == {'八年级': ['八年级-1', '八年级-3']}
        reopened.led_class_checks['八年级']['八年级-1'].setChecked(False)
        reopened.led_class_checks['八年级']['八年级-3'].setChecked(False)
        assert reopened._get_led_values(False) is None
        assert '至少选择一个显示班级' in reopened._led_validation_message
    finally:
        if reopened:
            reopened.close()
        widget.close()
        app.processEvents()


def test_desktop_uses_same_class_selection_and_default_includes_new_classes():
    from src.services.config_manager import ConfigManager
    from src.ui.desktop_display import render_desktop_frames
    values = {**ConfigManager.DEFAULT_CONFIG, 'led_visible_classes_by_grade': {'七年级': ['b']}}
    classes = [dict(class_id='a', grade_name='七年级', class_name='1班'),
               dict(class_id='b', grade_name='七年级', class_name='2班'),
               dict(class_id='c', grade_name='八年级', class_name='1班')]
    with patch('src.ui.desktop_display.render_led_pages', wraps=renderer.render_led_pages) as render:
        assert render_desktop_frames(values, {1: classes}, {}, (640, 480))
        assert [c['class_id'] for c in render.call_args.args[1]] == ['b', 'c']


def test_invalid_class_selection_is_rejected():
    import pytest
    from src.services.config_manager import load_led_setup, validate_led_setup
    for value in ([], {'七年级': 'b'}, {'七年级': [1]}, {'': ['b']}):
        screens, plans = load_led_setup(FakeConfig())
        screens[0]['settings']['led_visible_classes_by_grade'] = value
        with pytest.raises(ValueError, match='显示班级'):
            validate_led_setup(screens, plans)


def test_saved_missing_class_is_visible_and_does_not_match_a_replacement_id():
    from PyQt6.QtWidgets import QApplication
    from src.ui.settings_dialog import SettingsDialog
    from tests.test_settings_preview import FakeConfig as SettingsConfig, FakeLedService
    app = QApplication.instance() or QApplication([])
    cfg = SettingsConfig()
    cfg.set('led_visible_classes_by_grade', {'七年级': ['removed-id']})
    service = FakeLedService(grades=['七年级'])
    service.get_available_admin_classes = lambda school_id: [
        dict(class_id='new-id', grade_name='七年级', class_name='1班')]
    widget = SettingsDialog(cfg, led_service=service)
    try:
        assert '已失效' in widget.led_class_checks['七年级']['removed-id'].text()
        assert widget.led_class_checks['七年级']['removed-id'].isChecked()
        assert not widget.led_class_checks['七年级']['new-id'].isChecked()
        assert widget._get_led_values(False)['visible_classes_by_grade'] == {'七年级': ['removed-id']}
    finally:
        widget.close()
        app.processEvents()


def test_two_screens_display_different_classes_but_share_the_status(tmp_path):
    from tests.test_multi_screen_led import make_service
    from src.services import led_service
    service, config, bridges = make_service(tmp_path)
    try:
        service.db.upsert_led_class('40125', 1, 'extra', '一年级', '二班')
        for screen, cid in zip(config.values['led_screens'], ['1', 'extra']):
            screen['plan_id'] = 'low'
            screen['settings']['led_visible_classes_by_grade'] = {'一年级': [cid]}
        service.reconfigure(refresh=False)
        captures = []
        def render(title, classes, statuses, *args, **kwargs):
            captures.append(([c['class_id'] for c in classes], dict(statuses)))
            return renderer.render_led_pages(title, classes, statuses, *args, **kwargs)
        with patch.object(led_service, 'render_led_pages', side_effect=render):
            service.mark_dismissing('extra')
        assert any(ids == ['1', '2'] for ids, _ in captures)
        assert any(ids == ['extra', '2'] for ids, _ in captures)
        assert all(statuses[(1, 'extra')] == '放学中' for _, statuses in captures)
        assert len(bridges['south'].displays) == len(bridges['north'].displays) == 1
    finally:
        service.shutdown()
