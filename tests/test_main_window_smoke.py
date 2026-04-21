import os
import unittest

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication
    from src.services.system_status import RuntimeStatusStore
    from src.ui.main_window import MainWindow
    PYQT_AVAILABLE = True
except ModuleNotFoundError:
    QObject = object
    PYQT_AVAILABLE = False


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeConfig:
    def __init__(self):
        self._data = {
            "maintenance_pin": "1234",
            "maintenance_timeout_seconds": 300,
            "time_window_start": "16:30",
            "time_window_end": "18:30",
            "schedules": [],
        }

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def save(self):
        return None


class _FakeDB:
    def get_recent_logs(self):
        return []

    def get_devices(self):
        return []

    def get_all_mappings(self):
        return []


class _FakeBroadcastManager(QObject):
    if PYQT_AVAILABLE:
        log_updated = pyqtSignal(str, str, str, str, str)

    def __init__(self, status_store):
        super().__init__()
        self.status_store = status_store

    def process_swipe(self, card_id, ip):
        return None

    def is_within_time_window(self):
        return False

    def cleanup(self):
        return None


class _FakeUDPServer(QObject):
    if PYQT_AVAILABLE:
        card_swiped = pyqtSignal(str, str)
        device_updated = pyqtSignal(str, str, str, str)

    def start(self):
        return True

    def stop(self):
        return None


class _FakeSyncService:
    def force_sync(self):
        return None


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 not available in test environment")
class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_default_mode_is_guard_with_dashboard_visible(self):
        status_store = RuntimeStatusStore()
        window = MainWindow(
            _FakeConfig(),
            _FakeDB(),
            _FakeBroadcastManager(status_store),
            _FakeUDPServer(),
            _FakeSyncService(),
            status_store=status_store,
        )
        window.show()
        self._app.processEvents()

        self.assertEqual(window.current_mode, "guard")
        self.assertTrue(window.dashboard_view.isVisible())
        self.assertFalse(window.maintenance_panel.isVisible())

        window.close()


if __name__ == "__main__":
    unittest.main()
