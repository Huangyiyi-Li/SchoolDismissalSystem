import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
from src.services.config_manager import validate_led_setup, LedScreenConfig
from src.services.led_renderer import render_led_pages, render_club_led_pages
from tests.test_led_service import FakeConfig


@pytest.fixture(scope='module')
def app():
    if QApplication is None:
        pytest.skip('PyQt6 unavailable')
    return QApplication.instance() or QApplication([])


def setup():
    return ([{'id': 'pc', 'name': '电脑', 'enabled': True, 'plan_id': 'p',
              'settings': {'led_output_type': 'desktop', 'led_monitor': '',
                           'led_width': 3840, 'led_height': 2160}}],
            [{'id': 'p', 'name': '默认', 'settings': {'led_title_position': 'top'}}])


def test_pc_accepts_native_resolution_without_controller_and_defaults_dual():
    screens, plans = setup()
    screens[0]['settings']['led_controller_ip'] = ''
    validate_led_setup(screens, plans)
    cfg = LedScreenConfig(FakeConfig(), screens[0], plans[0])
    assert cfg.get('led_color_mode') == 'double'
    assert cfg.get('led_title_position') == 'top'


def test_led_still_has_controller_limits_and_title_position_validated():
    screens, plans = setup()
    screens[0]['settings']['led_output_type'] = 'led'
    with pytest.raises(ValueError):
        validate_led_setup(screens, plans)
    screens, plans = setup()
    plans[0]['settings']['led_title_position'] = 'bottom'
    with pytest.raises(ValueError):
        validate_led_setup(screens, plans)


@pytest.mark.parametrize('renderer,kind', [(render_led_pages, 1), (render_club_led_pages, 2)])
def test_top_title_is_horizontal_band_and_hidden_title_reclaims_space(tmp_path, renderer, kind):
    classes = [{'class_id': '1', 'class_type': kind, 'grade_name': '一年级', 'class_name': '一班', 'source_order': 0}]
    with patch('src.services.led_renderer._draw_title') as draw:
        paths = renderer('学校', classes, {}, tmp_path, width=640, height=360, title_position='top')
        box = draw.call_args.args[2]
        assert box[0] == box[1] == 0 and box[2] == 640
        assert 0 < box[3] < 180
        assert Image.open(paths[0]).size == (640, 360)
    with patch('src.services.led_renderer._draw_title') as draw:
        renderer('学校', classes, {}, tmp_path, title_position='top', show_title=False)
        draw.assert_not_called()


def test_desktop_is_not_dispatched_to_java_bridge(tmp_path):
    from src.services.led_service import MultiScreenLedService
    from src.database import DatabaseManager
    screens, plans = setup()
    cfg = FakeConfig({'led_screens': screens, 'led_display_plans': plans})
    with patch('src.services.led_service.JavaLedBridge.display') as send:
        service = MultiScreenLedService(cfg, DatabaseManager(str(tmp_path / 's.db')))
        try:
            assert service.outputs == {}
            service.mark_dismissing('1')
            send.assert_not_called()
            assert service.display_snapshot()['statuses'][(1, '1')] == '放学中'
        finally:
            service.shutdown()


def test_settings_switch_to_pc_defaults_and_keeps_shared_title(app):
    from tests.test_multi_screen_settings import dialog
    _, widget = dialog()
    try:
        assert hasattr(widget, 'led_output_combo'), 'output selector is required'
        widget.led_output_combo.setCurrentIndex(widget.led_output_combo.findData('desktop'))
        assert widget.led_color_mode_combo.currentData() == 'double'
        assert widget.led_width_edit.isReadOnly()
        widget.led_title_position_combo.setCurrentIndex(widget.led_title_position_combo.findData('top'))
        values = widget.screen_panel.values()
        assert values[0][0]['settings']['led_output_type'] == 'desktop'
        assert values[1][0]['settings']['led_title_position'] == 'top'
    finally:
        widget.close()


def test_monitor_pixels_accounts_for_windows_scaling(app):
    from src.ui.desktop_display import monitor_pixels
    from PyQt6.QtCore import QRect
    class Screen:
        def geometry(self): return QRect(0, 0, 1536, 864)
        def devicePixelRatio(self): return 1.25
    assert monitor_pixels(Screen()) == (1920, 1080)


def test_runtime_exit_and_next_session_and_monitor_loss(app):
    from concurrent.futures import Future
    from src.ui.desktop_display import DesktopDisplayManager, resolve_monitor
    class DB:
        def get_led_classes(self, school_id, class_type): return []
    class Service:
        db = DB()
        state = dict(active=False, session=1, statuses={}, class_types=(1,))
        def display_snapshot(self): return dict(self.state)
    class Immediate:
        def submit(self, *args):
            future = Future()
            future.set_result([])
            return future
        def shutdown(self, **kwargs): pass
    screens, plans = setup()
    cfg = FakeConfig({'led_screens': screens, 'led_display_plans': plans})
    manager = DesktopDisplayManager(cfg, Service())
    manager.timer.stop()
    manager.executor.shutdown()
    manager.executor = Immediate()
    try:
        manager.tick()
        assert not manager.windows
        manager.service.state['active'] = True
        manager.tick()
        assert manager.windows['pc'].isVisible()
        manager.windows['pc'].close()
        manager.tick()
        assert not manager.windows, 'Esc/close must not immediately reopen'
        manager.resume()
        assert 'pc' in manager.windows
        with patch('src.ui.desktop_display.resolve_monitor', return_value=None):
            manager.tick()
            assert not manager.windows
            assert manager.statuses['pc'] == '显示器未连接'
        manager.tick()
        assert 'pc' in manager.windows
        manager.service.state.update(active=False, session=2)
        manager.tick()
        assert not manager.windows
        manager.service.state.update(active=True, session=3)
        manager.tick()
        assert 'pc' in manager.windows
    finally:
        manager.shutdown()
        app.processEvents()


def test_monitor_selector_present_in_connection_form(app):
    from tests.test_multi_screen_settings import dialog
    _, widget = dialog()
    try:
        assert widget.led_connection_form.getWidgetPosition(widget.led_monitor_combo)[0] >= 0
    finally:
        widget.close()


def test_desktop_renders_all_three_states_at_native_size(app):
    from src.ui.desktop_display import render_desktop_frames
    screens, plans = setup()
    cfg = LedScreenConfig(FakeConfig(), screens[0], plans[0])
    classes = {1: [{'class_id': str(i), 'class_type': 1, 'grade_name': '一年级',
                   'class_name': f'{i}班', 'source_order': i} for i in range(1, 4)]}
    frames = render_desktop_frames(cfg.values, classes, {(1, '1'): '放学中', (1, '2'): '已放学'}, (1366, 768))
    w, h, data = frames[0]
    assert (w, h) == (1366, 768)
    colors = {tuple(data[i:i + 3]) for i in range(0, len(data), 3)}
    assert {(255, 0, 0), (255, 255, 0), (0, 255, 0)} <= colors


def test_pc_configuration_save_reopen_and_led_title_plan_shared(app):
    from tests.test_multi_screen_settings import dialog
    from src.ui.settings_dialog import SettingsDialog
    from tests.test_settings_preview import FakeLedService
    _, widget = dialog()
    reopened = None
    try:
        widget.led_title_position_combo.setCurrentIndex(1)
        widget.screen_panel.add_screen()
        widget.screen_panel.plan_combo.setCurrentIndex(0)
        widget.led_output_combo.setCurrentIndex(1)
        with patch('src.ui.settings_dialog.QMessageBox.information'):
            widget.save_settings()
        reopened = SettingsDialog(widget.config, led_service=FakeLedService())
        assert reopened.led_title_position_combo.currentData() == 'top'
        reopened.screen_panel.screen_list.setCurrentRow(1)
        assert reopened.led_output_combo.currentData() == 'desktop'
        assert reopened.led_color_mode_combo.currentData() == 'double'
        assert reopened.led_title_position_combo.currentData() == 'top'
        assert reopened.led_width_edit.isReadOnly()
    finally:
        if reopened: reopened.close()
        widget.close()


def test_render_in_flight_cannot_reopen_after_schedule_ends(app):
    from concurrent.futures import Future
    from src.ui.desktop_display import DesktopDisplayManager
    class DB:
        def get_led_classes(self, *args, **kwargs): return []
    class Service:
        db = DB()
        state = dict(active=True, session=1, statuses={}, class_types=(1,))
        def display_snapshot(self): return dict(self.state)
    class Deferred:
        def __init__(self): self.jobs = []
        def submit(self, *args):
            future = Future()
            self.jobs.append((future, args))
            return future
        def shutdown(self, **kwargs): pass
    screens, plans = setup()
    manager = DesktopDisplayManager(FakeConfig({'led_screens': screens, 'led_display_plans': plans}), Service())
    manager.timer.stop()
    manager.executor.shutdown()
    manager.executor = Deferred()
    try:
        with patch('src.ui.desktop_display.monitor_pixels', return_value=(1920, 1080)):
            manager.tick()
        assert manager.executor.jobs[0][1][-1] == (1920, 1080)
        manager.service.state.update(active=False, session=2)
        manager.executor.jobs[0][0].set_result([])
        app.processEvents()
        assert not manager.windows
        manager.service.state.update(active=True, session=3)
        with patch('src.ui.desktop_display.monitor_pixels', return_value=(2560, 1440)):
            manager.tick()
        assert manager.executor.jobs[1][1][-1] == (2560, 1440)
        manager.service.state['active'] = False
        manager.executor.jobs[1][0].set_result([])
    finally:
        manager.shutdown()


def test_fullscreen_test_window_escape_and_paging(app):
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    from src.ui.desktop_display import DesktopDisplayWindow, resolve_monitor
    window = DesktopDisplayWindow(preview=True)
    exited = []
    window.dismissed.connect(lambda: exited.append(True))
    try:
        window.set_frames([(2, 2, bytes([255, 0, 0] * 4)), (2, 2, bytes([0, 255, 0] * 4))], 5)
        window.present(resolve_monitor(''))
        window.next_page()
        assert window.index == 1
        QTest.keyClick(window, Qt.Key.Key_Escape)
        assert exited and not window.isVisible() and not window.timer.isActive()
    finally:
        window.close()


def test_fullscreen_window_has_mouse_close_button(app):
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    from src.ui.desktop_display import DesktopDisplayWindow, resolve_monitor
    window = DesktopDisplayWindow()
    closed = []
    window.dismissed.connect(lambda: closed.append(True))
    try:
        window.present(resolve_monitor(''))
        assert window.close_button.isVisible()
        QTest.mouseClick(window.close_button, Qt.MouseButton.LeftButton)
        assert closed and not window.isVisible()
    finally:
        window.close()


def test_duplicate_enabled_pc_monitor_rejected_but_disabled_draft_allowed():
    from copy import deepcopy
    screens, plans = setup()
    other = deepcopy(screens[0])
    other['id'] = 'other'
    screens.append(other)
    with pytest.raises(ValueError, match='显示器'):
        validate_led_setup(screens, plans)
    other['enabled'] = False
    validate_led_setup(screens, plans)


def test_restore_auto_layout_resets_relative_size(app):
    from tests.test_multi_screen_settings import dialog
    _, widget = dialog()
    try:
        widget.led_table_scale_slider.setValue(70)
        widget.led_title_scale_slider.setValue(60)
        assert hasattr(widget, 'led_auto_layout_btn')
        widget.led_auto_layout_btn.click()
        assert widget.led_table_scale_slider.value() == 100
        assert widget.led_title_scale_slider.value() == 100
        assert widget._preview_state.dirty
    finally:
        widget.close()
