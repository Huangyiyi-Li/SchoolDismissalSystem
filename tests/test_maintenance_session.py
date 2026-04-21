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

    def test_session_relocks_after_timeout(self):
        controller = MaintenanceSessionController(pin="1234", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 10, 0, 0)
        controller.unlock("1234", now=now)

        expired = now + datetime.timedelta(seconds=61)

        self.assertFalse(controller.is_unlocked(now=expired))


if __name__ == "__main__":
    unittest.main()

