import unittest
import sys
import types


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


class FakeTtsWorker:
    def __init__(self):
        self.texts = []

    def add_text(self, text):
        self.texts.append(text)


class ManualDismissalTests(unittest.TestCase):
    def make_manager(self, class_info):
        manager = BroadcastManager.__new__(BroadcastManager)
        manager.db = FakeDb(class_info)
        manager.api_service = None
        manager.manual_command_history = set()
        manager.tts_worker = FakeTtsWorker()
        manager.logged_events = []
        manager._log_event = lambda *args: manager.logged_events.append(args)
        return manager

    def test_unknown_class_without_name_fails_without_fake_broadcast(self):
        manager = self.make_manager((None, "123", None, 1, None, None))

        result = manager.process_manual_dismissal({"classType": 1, "classId": "123"})

        self.assertEqual(result, {"result": "fail", "message": "class not found: 123"})
        self.assertEqual(manager.tts_worker.texts, [])
        self.assertEqual(
            manager.logged_events,
            [("123", "未知班级", "跳过", "服务端指令缺少班级信息")],
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


if __name__ == "__main__":
    unittest.main()
