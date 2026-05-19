import unittest

from src.services.broadcast_mode import get_effective_window_signature


class BroadcastModeTests(unittest.TestCase):
    def test_test_mode_uses_synthetic_window_outside_dismissal_time(self):
        self.assertEqual(get_effective_window_signature(None, True), "TestMode")

    def test_normal_mode_still_requires_dismissal_window(self):
        self.assertIsNone(get_effective_window_signature(None, False))

    def test_active_window_is_preserved_in_test_mode(self):
        self.assertEqual(get_effective_window_signature("WD2_16:30-17:10", True), "WD2_16:30-17:10")


if __name__ == "__main__":
    unittest.main()
