import datetime
import unittest

from src.ui.maintenance_session import MaintenanceSessionController


class MaintenanceSessionControllerTests(unittest.TestCase):
    def test_valid_pin_unlocks_session(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)

        unlocked = controller.unlock("1234", now=now)

        self.assertTrue(unlocked)
        self.assertTrue(controller.is_unlocked(now=now))

    def test_wrong_pin_remains_locked(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)

        unlocked = controller.unlock("0000", now=now)

        self.assertFalse(unlocked)
        self.assertFalse(controller.is_unlocked(now=now))

    def test_session_relocks_after_timeout(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)
        controller.unlock("1234", now=now)

        expired = now + datetime.timedelta(seconds=61)

        self.assertFalse(controller.is_unlocked(now=expired))

    def test_is_unlocked_true_at_exact_deadline_boundary(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)
        controller.unlock("1234", now=now)
        deadline = now + datetime.timedelta(seconds=60)

        self.assertTrue(controller.is_unlocked(now=deadline))

    def test_touch_extends_active_deadline(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)
        controller.unlock("1234", now=now)
        touch_time = now + datetime.timedelta(seconds=30)
        controller.touch(now=touch_time)

        original_expiry_plus_one = now + datetime.timedelta(seconds=61)
        extended_expiry_plus_one = touch_time + datetime.timedelta(seconds=61)

        self.assertTrue(controller.is_unlocked(now=original_expiry_plus_one))
        self.assertFalse(controller.is_unlocked(now=extended_expiry_plus_one))

    def test_mixed_naive_and_aware_datetimes_do_not_crash(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        aware_now = datetime.datetime(2026, 4, 21, 10, 0, 0, tzinfo=datetime.timezone.utc)
        controller.unlock("1234", now=aware_now)

        # This used to be a potential TypeError path if naive/aware compare was not normalized.
        self.assertTrue(controller.is_unlocked(now=datetime.datetime(2026, 4, 21, 10, 0, 30)))


if __name__ == "__main__":
    unittest.main()
