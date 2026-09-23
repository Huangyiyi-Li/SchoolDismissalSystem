import threading
import time
from pathlib import Path
from unittest.mock import patch

from src.database import DatabaseManager
from src.services import led_service
from tests.test_led_service import FakeConfig, FakeBridge, FakeTimerFactory


def test_migration_preserves_legacy_and_is_independent():
    from src.services import config_manager
    migrate = getattr(config_manager, 'load_led_setup', None)
    assert callable(migrate), 'single screen settings need a multi-screen migration'
    config = FakeConfig({'led_visible_grades': ['一年级'], 'led_grade_filter_mode': 'selected'})
    screens, plans = migrate(config)
    assert len(screens) == len(plans) == 1
    assert screens[0]['settings']['led_controller_ip'] == '192.168.100.1'
    assert plans[0]['settings']['led_visible_grades'] == ['一年级']
    plans[0]['settings']['led_visible_grades'].append('二年级')
    assert config.get('led_visible_grades') == ['一年级']


def test_grade_selection_overrides_shared_plan_for_one_screen():
    from src.services.config_manager import LedScreenConfig
    parent = FakeConfig()
    plan = {'id': 'shared', 'settings': {'led_grade_filter_mode': 'selected',
                                         'led_visible_grades': ['一年级']}}
    first = {'id': 'first', 'enabled': True, 'settings': {
        'led_grade_filter_mode': 'selected', 'led_visible_grades': ['二年级']}}
    second = {'id': 'second', 'enabled': True, 'settings': {}}
    assert LedScreenConfig(parent, first, plan).get('led_visible_grades') == ['二年级']
    assert LedScreenConfig(parent, second, plan).get('led_visible_grades') == ['一年级']


def test_grade_pages_are_independent_for_screens_sharing_a_plan():
    from src.services.config_manager import LedScreenConfig
    plan = {'id': 'shared', 'settings': {}}
    first = {'enabled': True, 'settings': {'led_grade_pages': [['二年级', '三年级'], ['四年级']]}}
    second = {'enabled': True, 'settings': {'led_grade_pages': [['四年级'], ['五年级']]}}
    parent = FakeConfig({})
    assert LedScreenConfig(parent, first, plan).get('led_grade_pages') == [['二年级', '三年级'], ['四年级']]
    assert LedScreenConfig(parent, second, plan).get('led_grade_pages') == [['四年级'], ['五年级']]


def make_service(tmp_path, async_output=False, bridges=None):
    cls = getattr(led_service, 'MultiScreenLedService', None)
    assert cls is not None, 'a multi-screen status owner and independent outputs are required'
    db = DatabaseManager(str(tmp_path / 'school.db'))
    for i, grade in enumerate(['一年级', '二年级', '三年级']):
        db.upsert_led_class('40125', 1, str(i + 1), grade, grade + '一班', source_order=i)
    config = FakeConfig({'school_id': '40125', 'led_screens': [
        {'id': 'south', 'name': '南门屏', 'enabled': True, 'plan_id': 'low',
         'settings': {'led_controller_ip': '192.168.100.1'}},
        {'id': 'north', 'name': '北门屏', 'enabled': True, 'plan_id': 'high',
         'settings': {'led_controller_ip': '192.168.100.2'}}],
        'led_display_plans': [
            {'id': 'low', 'name': '低年级', 'settings': {'led_grade_filter_mode': 'selected', 'led_visible_grades': ['一年级', '二年级']}},
            {'id': 'high', 'name': '高年级', 'settings': {'led_grade_filter_mode': 'selected', 'led_visible_grades': ['三年级']}}]})
    bridges = bridges or {'south': FakeBridge(), 'north': FakeBridge()}
    service = cls(config, db, bridge_factory=lambda screen: bridges[screen['id']],
                  output_dir=tmp_path / 'pages', timer_factory=FakeTimerFactory(),
                  output_submitter=None if async_output else lambda task: task())
    return service, config, bridges


def test_split_and_overlapping_grades_share_one_persisted_status(tmp_path):
    service, config, bridges = make_service(tmp_path)
    try:
        captures = []
        original = led_service.render_led_pages
        def render(*args, **kwargs):
            captures.append(([x['grade_name'] for x in args[1]], dict(args[2])))
            return original(*args, **kwargs)
        with patch.object(led_service, 'render_led_pages', side_effect=render), patch.object(service.db, 'save_led_class_status', wraps=service.db.save_led_class_status) as save:
            service.mark_dismissing('1')
            assert save.call_count == 1
        assert len(bridges['south'].displays) == len(bridges['north'].displays) == 1
        assert any(grades == ['一年级', '二年级'] for grades, _ in captures)
        assert any(grades == ['三年级'] for grades, _ in captures)
        config.values['led_screens'][1]['plan_id'] = 'low'
        service.reconfigure()
        assert service.outputs['north'].config.get('led_visible_grades') == ['一年级', '二年级']
        assert service.get_status('1') == '放学中'
        assert service.outputs['north'].get_statuses_snapshot() == service.get_statuses_snapshot()
    finally:
        service.shutdown()


def test_blocked_screen_does_not_block_other_screen(tmp_path):
    entered, release, received = threading.Event(), threading.Event(), threading.Event()
    class Slow(FakeBridge):
        def display(self, *args, **kwargs):
            entered.set()
            release.wait(3)
            return super().display(*args, **kwargs)
    class Fast(FakeBridge):
        def display(self, *args, **kwargs):
            result = super().display(*args, **kwargs)
            received.set()
            return result
    service, _, _ = make_service(tmp_path, True, {'south': Slow(), 'north': Fast()})
    try:
        service.mark_dismissing('1')
        assert entered.wait(2)
        assert received.wait(2), 'north must update while south is still blocked'
    finally:
        release.set()
        service.shutdown()
        time.sleep(.1)


def test_restore_one_screen_keeps_school_status_and_other_screen(tmp_path):
    service, _, bridges = make_service(tmp_path)
    try:
        service.mark_dismissing('1')
        result = service.restore_screen('south')
        assert result.ok
        assert service.get_status('1') == '放学中'
        assert bridges['south'].clears
        assert not bridges['north'].clears
    finally:
        service.shutdown()


def test_disabled_screen_never_receives_refresh_and_reenable_keeps_status(tmp_path):
    service, config, bridges = make_service(tmp_path)
    try:
        config.values['led_screens'][0]['enabled'] = False
        service.reconfigure()
        count = len(bridges['south'].displays)
        service.outputs['south'].refresh()  # a refresh already queued before disable
        service.mark_dismissing('1')
        assert len(bridges['south'].displays) == count
        config.values['led_screens'][0]['enabled'] = True
        service.reconfigure()
        assert len(bridges['south'].displays) > count
        assert service.get_status('1') == '放学中'
    finally:
        service.shutdown()


def test_schedule_exit_resets_database_once_and_restores_both(tmp_path):
    service, _, bridges = make_service(tmp_path)
    try:
        service.mark_dismissing('1')
        with patch.object(service.db, 'clear_led_class_statuses', wraps=service.db.clear_led_class_statuses) as clear:
            service.set_dismissal_active(False)
            assert clear.call_count == 1
        assert service.get_status('1') == ''
        assert bridges['south'].clears and bridges['north'].clears
        service.set_dismissal_active(True, {1})
        service.mark_dismissing('2')
        assert service.get_status('2') == '放学中'
    finally:
        service.shutdown()


def test_remove_and_change_address_restore_old_target(tmp_path):
    service, config, bridges = make_service(tmp_path)
    try:
        service.mark_dismissing('1')
        config.values['led_screens'].pop(1)
        config.values['led_screens'][0]['settings']['led_controller_ip'] = '192.168.100.3'
        service.reconfigure()
        assert ('192.168.100.2', 5005) in bridges['north'].clears
        assert ('192.168.100.1', 5005) in bridges['south'].clears
        assert bridges['south'].displays[-1][0] == '192.168.100.3'
        assert 'north' not in service.outputs
    finally:
        service.shutdown()


def test_failed_output_retries_latest_status_on_schedule_tick(tmp_path):
    service, _, bridges = make_service(tmp_path)
    try:
        from src.services.led_bridge_client import BridgeResult
        bridges['south'].display_results = [BridgeResult(False, 'offline')]
        service.mark_dismissing('1')
        assert service.screen_statuses()['south'] == '通信失败'
        service.outputs['south']._next_window_refresh_retry_at = None
        service.set_dismissal_active(True, {1})
        assert service.screen_statuses()['south'] == '最近通信成功'
        assert service.outputs['south'].get_statuses_snapshot() == service.get_statuses_snapshot()
    finally:
        service.shutdown()


def test_midnight_refresh_keeps_new_day_status(tmp_path):
    import datetime
    service, _, bridges = make_service(tmp_path)
    try:
        tomorrow = service.clock() + datetime.timedelta(days=1)
        service.clock = lambda: tomorrow
        for output in service.outputs.values():
            output.clock = lambda: tomorrow
        service.mark_dismissing('1')
        assert service.outputs['south']._statuses.get((1, '1')) == '放学中'
    finally:
        service.shutdown()


def test_rotating_failure_is_visible_and_retried(tmp_path):
    from src.services.led_bridge_client import BridgeResult
    service, _, bridges = make_service(tmp_path)
    try:
        output = service.outputs['south']
        output._start_display_session('192.168.100.1', 5005, [Path('a.bmp'), Path('b.bmp')], 5)
        bridges['south'].display_results = [BridgeResult(False, 'disconnected')]
        output._run_display_rotation(output._display_generation)
        assert service.screen_statuses()['south'] == '通信失败'
        assert output._window_refresh_pending
    finally:
        service.shutdown()


def test_readding_same_controller_reuses_its_queue(tmp_path):
    service, config, bridges = make_service(tmp_path)
    try:
        old = service.outputs['north']
        definition = config.values['led_screens'].pop()
        service.reconfigure()
        definition['id'] = 'north-new'
        config.values['led_screens'].append(definition)
        service.reconfigure()
        assert service.outputs['north-new'] is old
        service.mark_dismissing('3')
        assert bridges['north'].displays[-1][0] == '192.168.100.2'
    finally:
        service.shutdown()


def test_swapping_screen_addresses_preserves_physical_output_queues(tmp_path):
    service, config, bridges = make_service(tmp_path)
    try:
        south, north = service.outputs['south'], service.outputs['north']
        service.mark_dismissing('1')
        config.values['led_screens'][0]['settings']['led_controller_ip'] = '192.168.100.2'
        config.values['led_screens'][1]['settings']['led_controller_ip'] = '192.168.100.1'
        service.reconfigure()
        assert service.outputs['south'] is north
        assert service.outputs['north'] is south
        assert not bridges['south'].clears and not bridges['north'].clears
    finally:
        service.shutdown()


def test_removed_and_disabled_screen_restore_failures_retry(tmp_path):
    from src.services.led_bridge_client import BridgeResult
    service, config, bridges = make_service(tmp_path)
    try:
        service.mark_dismissing('1')
        bridges['north'].clear_results = [BridgeResult(False, 'offline')]
        bridges['south'].clear_results = [BridgeResult(False, 'offline')]
        config.values['led_screens'].pop(1)
        config.values['led_screens'][0]['enabled'] = False
        service.reconfigure()
        before = {sid: len(b.clears) for sid, b in bridges.items()}
        service.set_dismissal_active(True, {1})
        assert all(len(b.clears) > before[sid] for sid, b in bridges.items())
    finally:
        service.shutdown()


def test_restore_failure_updates_status_and_retries(tmp_path):
    from src.services.led_bridge_client import BridgeResult
    service, _, bridges = make_service(tmp_path)
    try:
        service.mark_dismissing('1')
        bridges['south'].clear_results = [BridgeResult(False, 'offline')]
        service.restore_screen('south')
        assert service.screen_statuses()['south'] == '通信失败'
        before = len(bridges['south'].clears)
        service.set_dismissal_active(True, {1})
        assert len(bridges['south'].clears) > before
    finally:
        service.shutdown()


def test_testing_retired_endpoint_reuses_worker(tmp_path):
    service, config, _ = make_service(tmp_path)
    try:
        output = service.outputs['north']
        config.values['led_screens'].pop(1)
        service.reconfigure()
        assert service._target_output('192.168.100.2', 5005) is output
    finally:
        service.shutdown()


def test_latest_config_wins_when_save_reverts_a_queued_change(tmp_path):
    service, config, _ = make_service(tmp_path)
    try:
        tasks = []
        output = service.outputs['south']
        output._submitter = tasks.append
        config.values['led_screens'][0]['settings']['led_width'] = 640
        service.reconfigure()
        config.values['led_screens'][0]['settings']['led_width'] = 1024
        service.reconfigure()
        while tasks:
            tasks.pop(0)()
        assert output.config.get('led_width') == 1024
    finally:
        service.shutdown()


def test_owner_does_not_repeat_successful_output_refresh_as_a_retry(tmp_path):
    import datetime
    service, _, bridges = make_service(tmp_path)
    try:
        service.set_dismissal_active(False)
        service.set_dismissal_active(True, {1})
        before = len(bridges['south'].displays)
        later = service.clock() + datetime.timedelta(seconds=11)
        service.clock = lambda: later
        service.set_dismissal_active(True, {1})
        assert len(bridges['south'].displays) == before
    finally:
        service.shutdown()
