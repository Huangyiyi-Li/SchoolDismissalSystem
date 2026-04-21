import datetime
import unittest

from src.services.broadcast_policy import evaluate_swipe


class BroadcastPolicyTests(unittest.TestCase):
    def test_broadcast_count_affects_voice_text_repetition(self):
        now = datetime.datetime(2026, 4, 21, 16, 40)
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-1",
            window_signature="dynamic:2:16:30-18:30",
            now=now,
            voice_history={},
            api_push_history={},
            deduplication_interval_seconds=300,
            broadcast_count=2,
            test_mode=True,
            api_service_available=True,
        )

        self.assertTrue(decision.should_voice)
        self.assertEqual(decision.voice_text, "一年级一班正在放学，一年级一班正在放学")
        self.assertFalse(decision.should_push_api)
        self.assertIn("测试模式", decision.reason)

    def test_duplicate_window_leads_no_voice_and_duplicate_reason(self):
        now = datetime.datetime(2026, 4, 21, 16, 45)
        window_sig = "dynamic:2:16:30-18:30"
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-1",
            window_signature=window_sig,
            now=now,
            voice_history={"一年级一班": window_sig},
            api_push_history={},
            deduplication_interval_seconds=300,
            broadcast_count=3,
            test_mode=True,
            api_service_available=True,
        )

        self.assertFalse(decision.should_voice)
        self.assertEqual(decision.action, "语音跳过/测试模式")
        self.assertIn("重复播报", decision.reason)

    def test_non_time_window_path_skips_swipe(self):
        now = datetime.datetime(2026, 4, 21, 12, 0)
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-2",
            window_signature=None,
            now=now,
            voice_history={},
            api_push_history={},
            deduplication_interval_seconds=300,
            broadcast_count=3,
            test_mode=False,
            api_service_available=True,
        )

        self.assertFalse(decision.should_voice)
        self.assertFalse(decision.should_push_api)
        self.assertEqual(decision.action, "跳过")
        self.assertEqual(decision.reason, "非播报时段")

    def test_invalid_card_path_skips_swipe(self):
        now = datetime.datetime(2026, 4, 21, 16, 40)
        decision = evaluate_swipe(
            class_name=None,
            class_id=None,
            card_id="card-3",
            window_signature="dynamic:2:16:30-18:30",
            now=now,
            voice_history={},
            api_push_history={},
            deduplication_interval_seconds=300,
            broadcast_count=3,
            test_mode=False,
            api_service_available=True,
        )

        self.assertFalse(decision.should_voice)
        self.assertFalse(decision.should_push_api)
        self.assertEqual(decision.action, "跳过")
        self.assertEqual(decision.reason, "无效卡号")

    def test_api_unavailable_path_marks_reason(self):
        now = datetime.datetime(2026, 4, 21, 16, 41)
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-4",
            window_signature="dynamic:2:16:30-18:30",
            now=now,
            voice_history={},
            api_push_history={},
            deduplication_interval_seconds=300,
            broadcast_count=1,
            test_mode=False,
            api_service_available=False,
        )

        self.assertTrue(decision.should_voice)
        self.assertFalse(decision.should_push_api)
        self.assertIn("无API服务", decision.reason)

    def test_cooldown_edge_path_marks_cooldown(self):
        now = datetime.datetime(2026, 4, 21, 16, 42)
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-5",
            window_signature="dynamic:2:16:30-18:30",
            now=now,
            voice_history={},
            api_push_history={"card-5": now},
            deduplication_interval_seconds=300,
            broadcast_count=1,
            test_mode=False,
            api_service_available=True,
        )

        self.assertTrue(decision.should_voice)
        self.assertFalse(decision.should_push_api)
        self.assertIn("推送冷却", decision.reason)

    def test_test_mode_with_cooldown_keeps_cooldown_reason(self):
        now = datetime.datetime(2026, 4, 21, 16, 43)
        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="1",
            card_id="card-6",
            window_signature="dynamic:2:16:30-18:30",
            now=now,
            voice_history={},
            api_push_history={"card-6": now},
            deduplication_interval_seconds=300,
            broadcast_count=1,
            test_mode=True,
            api_service_available=True,
        )

        self.assertTrue(decision.should_voice)
        self.assertFalse(decision.should_push_api)
        self.assertIn("推送冷却", decision.reason)


if __name__ == "__main__":
    unittest.main()
