import os
import unittest
from unittest.mock import patch

try:
    from PyQt6.QtWidgets import QApplication
    from src.ui.device_manager_dialog import DeviceManagerDialog
    PYQT_AVAILABLE = True
except ModuleNotFoundError:
    QApplication = None
    PYQT_AVAILABLE = False


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeDB:
    def __init__(self):
        self.devices = []

    def get_devices(self):
        return list(self.devices)

    def upsert_device(self, ip, name=None):
        return True


class _FakeConfig:
    def get(self, key, default=None):
        if key == "device_network_command_port":
            return 1000
        if key == "device_network_discovery_port":
            return 51006
        return default


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 not available in test environment")
class DeviceManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_configure_network_opens_manual_dialog_without_selected_device(self):
        dialog = DeviceManagerDialog(_FakeDB(), _FakeConfig())

        with patch("src.ui.device_network_dialog.DeviceNetworkDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = 0

            dialog.configure_device_network()

        kwargs = dialog_cls.call_args.kwargs
        self.assertEqual(kwargs["current_ip"], "")
        self.assertEqual(kwargs["current_name"], "未检测设备")
        self.assertEqual(kwargs["occupied_ips"], [])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
