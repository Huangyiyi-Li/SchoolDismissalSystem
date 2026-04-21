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
        self.assertEqual(decision.action, "语音跳过")
        self.assertIn("重复播报", decision.reason)


if __name__ == "__main__":
    unittest.main()
