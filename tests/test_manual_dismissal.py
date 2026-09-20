import unittest
import sys
import types
from unittest.mock import patch


qtcore = types.ModuleType("PyQt6.QtCore")
qtcore.QObject = object
qtcore.pyqtSignal = lambda *args, **kwargs: None
qtcore.pyqtSlot = lambda *args, **kwargs: (lambda func: func)
qtcore.QThread = object
pyqt6 = types.ModuleType("PyQt6")
sys.modules.setdefault("PyQt6", pyqt6)
sys.modules.setdefault("PyQt6.QtCore", qtcore)
sys.modules.setdefault("pyttsx3", types.ModuleType("pyttsx3"))

from src.services.broadcast_manager import BroadcastManager


class FakeDb:
    def __init__(self, class_info):
        self.class_info = class_info

    def get_class_info_by_class(self, class_id, class_type=None):
        return self.class_info

    def get_class_info_by_card(self, card_id):
        return self.class_info

    def get_led_classes(self, school_id=None, class_type=1):
        class_name, class_id, stored_school_id, class_type, show_name, voice_name = self.class_info
        if not class_name or int(class_type or 0) not in (1, 2):
            return []
        return [
            {
                "school_id": stored_school_id,
                "class_type": class_type,
                "class_id": class_id,
                "grade_name": "一年级",
                "class_name": class_name,
                "class_show_name": show_name,
                "class_voice_name": voice_name,
            }
        ]


class FakeConfig:
    def __init__(self, values=None):
        self.values = {
            "test_mode": True,
            "deduplication_interval_seconds": 300,
            **(values or {}),
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeTtsWorker:
    def __init__(self):
        self.texts = []

    def add_text(self, text):
        self.texts.append(text)


class FakeApiService:
    def __init__(self):
        self.pushes = []

    def push_dismissal_notice(self, *args, **kwargs):
        self.pushes.append((args, kwargs))
        return True


class FakeLedService:
    def __init__(self):
        self.updates = []
        self.window_states = []
        self.test_modes = []

    def mark_dismissing(self, class_id, class_type=1):
        self.updates.append((int(class_type), class_id))

    def set_dismissal_active(self, active):
        self.window_states.append(active)

    def set_test_mode(self, enabled):
        self.test_modes.append(bool(enabled))


class ImmediateThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class ManualDismissalTests(unittest.TestCase):
    def make_manager(self, class_info):
        manager = BroadcastManager.__new__(BroadcastManager)
        manager.db = FakeDb(class_info)
        manager.api_service = None
        manager.manual_command_history = set()
        manager.tts_worker = FakeTtsWorker()
        manager.led_service = FakeLedService()
        manager.logged_events = []

        def log_event(card_id, class_name, action, reason, **kwargs):
            event = {
                "card_id": card_id,
                "class_name": class_name,
                "action": action,
                "reason": reason,
            }
            event.update(kwargs)
            manager.logged_events.append(event)

        manager._log_event = log_event
        return manager

    def test_unknown_class_without_name_fails_without_fake_broadcast(self):
        manager = self.make_manager((None, "123", None, 1, None, None))

        result = manager.process_manual_dismissal({"classType": 1, "classId": "123"})

        self.assertEqual(result, {"result": "fail", "message": "class not found: 123"})
        self.assertEqual(manager.tts_worker.texts, [])
        self.assertEqual(
            manager.logged_events,
            [
                {
                    "card_id": "",
                    "class_name": "未知班级",
                    "action": "跳过",
                    "reason": "服务端指令缺少班级信息",
                    "class_type": 1,
                    "source": "服务端指令",
                    "source_detail": "classId=123",
                }
            ],
        )

    def test_command_payload_class_voice_name_can_broadcast_without_local_mapping(self):
        manager = self.make_manager((None, "123", None, 1, None, None))

        result = manager.process_manual_dismissal(
            {
                "classType": 1,
                "classId": "123",
                "classVoiceName": "一年级一班",
            }
        )

        self.assertEqual(result, {"result": "success"})
        self.assertEqual(manager.tts_worker.texts, ["一年级一班正在放学"])
        self.assertEqual(manager.logged_events[0]["source"], "服务端指令")
        self.assertEqual(manager.logged_events[0]["source_detail"], "classId=123")

    def test_successful_server_command_reports_back_through_push_notice_api(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        api = FakeApiService()
        manager.api_service = api

        with patch("threading.Thread", ImmediateThread):
            result = manager.process_manual_dismissal(
                {
                    "classType": 1,
                    "classId": "123",
                    "dismissalStatus": 1,
                    "triggerTeacherId": "T01",
                    "triggerTeacherName": "王老师",
                }
            )

        self.assertEqual(result, {"result": "success"})
        self.assertEqual(
            api.pushes,
            [
                (
                    ("123", None),
                    {
                        "dismissal_status": 1,
                        "class_type": 1,
                        "trigger_type": 2,
                        "trigger_teacher_id": "T01",
                        "trigger_teacher_name": "王老师",
                    },
                )
            ],
        )
        self.assertEqual(manager.led_service.updates, [(1, "123")])

    def test_server_command_activates_legacy_led_adapter_without_config(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        result = manager.process_manual_dismissal({"classType": 1, "classId": "123"})
        self.assertEqual(result["result"], "success")
        self.assertEqual(manager.led_service.window_states, [True])

    def test_led_failure_does_not_block_manual_voice_or_result(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))

        def fail(_class_id):
            raise RuntimeError("LED offline")

        manager.led_service.mark_dismissing = fail

        result = manager.process_manual_dismissal({"classType": 1, "classId": "123"})

        self.assertEqual(result, {"result": "success"})
        self.assertEqual(manager.tts_worker.texts, ["一年级一班正在放学"])

    def test_club_command_updates_club_led_status(self):
        manager = self.make_manager(("足球社团", "201", "40125", 2, "足球社团", "足球社团"))

        result = manager.process_manual_dismissal({"classType": 2, "classId": "201"})

        self.assertEqual(result, {"result": "success"})
        self.assertEqual(manager.led_service.updates, [(2, "201")])

    def test_missing_payload_class_type_uses_local_administrative_type_for_led(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))

        result = manager.process_manual_dismissal({"classId": "123"})

        self.assertEqual(result, {"result": "success"})
        self.assertEqual(manager.led_service.updates, [(1, "123")])

    def test_hidden_led_grade_swipe_still_queues_voice_and_led_status(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        manager.config = FakeConfig(
            {
                "led_grade_filter_mode": "selected",
                "led_visible_grades": ["二年级"],
            }
        )
        manager.voice_history = {}
        manager.api_push_history = {}

        manager.process_swipe("CARD-1", "192.168.1.20")

        self.assertEqual(manager.led_service.updates, [(1, "123")])
        self.assertEqual(manager.tts_worker.texts, ["一年级一班正在放学"])

    def test_test_mode_activates_led_when_administrative_window_is_inactive(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        manager.config = FakeConfig({"test_mode": True})
        manager.get_current_window_signature = lambda class_type=None: None

        active = manager.sync_led_window_state()

        self.assertTrue(active)
        self.assertEqual(manager.led_service.window_states, [True])
        self.assertEqual(manager.led_service.test_modes, [True])

    def test_normal_mode_restores_led_when_administrative_window_is_inactive(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        manager.config = FakeConfig({"test_mode": False})
        manager.get_current_window_signature = lambda class_type=None: None

        active = manager.sync_led_window_state()

        self.assertFalse(active)
        self.assertEqual(manager.led_service.window_states, [False])

    def test_simulated_swipe_in_test_mode_uses_catalog_and_triggers_voice_and_led(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        manager.config = FakeConfig({"test_mode": True, "school_id": "40125"})
        manager.get_current_window_signature = lambda class_type=None: None

        result = manager.simulate_class_swipe("123")

        self.assertEqual(result, {"result": "success", "message": "已模拟一年级一班刷卡"})
        self.assertEqual(manager.tts_worker.texts, ["一年级一班正在放学"])
        self.assertEqual(manager.led_service.window_states, [True])
        self.assertEqual(manager.led_service.updates, [(1, "123")])
        self.assertEqual(manager.logged_events[0]["source"], "模拟刷卡")
        self.assertEqual(manager.logged_events[0]["source_detail"], "classId=123")

    def test_simulated_swipe_is_rejected_outside_test_mode(self):
        manager = self.make_manager(("一年级一班", "123", "40125", 1, "一(1)班", "一年级一班"))
        manager.config = FakeConfig({"test_mode": False, "school_id": "40125"})

        result = manager.simulate_class_swipe("123")

        self.assertEqual(result, {"result": "fail", "message": "请先开启测试模式"})
        self.assertEqual(manager.tts_worker.texts, [])
        self.assertEqual(manager.led_service.updates, [])

    def test_simulated_swipe_rejects_class_missing_from_led_catalog(self):
        manager = self.make_manager((None, "123", "40125", 1, None, None))
        manager.config = FakeConfig({"test_mode": True, "school_id": "40125"})

        result = manager.simulate_class_swipe("404")

        self.assertEqual(result, {"result": "fail", "message": "未找到该行政班，请先同步学校数据"})
        self.assertEqual(manager.tts_worker.texts, [])

    def test_simulated_club_swipe_triggers_club_voice_and_led_status(self):
        manager = self.make_manager(
            ("足球社团", "201", "40125", 2, "足球社团", "足球社团")
        )
        manager.config = FakeConfig({"test_mode": True, "school_id": "40125"})
        manager.get_current_window_signature = lambda class_type=None: None

        result = manager.simulate_class_swipe("201", class_type=2)

        self.assertEqual(result["result"], "success")
        self.assertEqual(manager.tts_worker.texts, ["足球社团正在放学"])
        self.assertEqual(manager.led_service.updates, [(2, "201")])
        self.assertEqual(manager.logged_events[0]["class_type"], 2)


if __name__ == "__main__":
    unittest.main()
