import datetime
import unittest

try:
    from src.services.udp_server import UDPServerService
    PYQT_AVAILABLE = True
except ModuleNotFoundError:
    UDPServerService = object
    PYQT_AVAILABLE = False


class _FakeDB:
    def __init__(self):
        self.device_names = {}

    def upsert_device(self, ip, name=None, last_seen=None):
        self.device_names.setdefault(ip, f"Device-{ip.split('.')[-1]}")
        return True

    def get_device_name(self, ip):
        return self.device_names.get(ip, ip)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 not available in test environment")
class TCPDevicePresenceTests(unittest.TestCase):
    def test_tcp_connection_keeps_device_online_without_recent_swipe(self):
        service = UDPServerService(db_manager=_FakeDB())
        service._mark_tcp_connected("192.168.199.66")
        service.devices["192.168.199.66"] = datetime.datetime.now() - datetime.timedelta(hours=1)

        service.check_offline_devices()

        self.assertEqual(service.count_online_devices(), 1)
        self.assertIn("192.168.199.66", service.tcp_connection_counts)

    def test_tcp_disconnect_marks_device_offline_immediately(self):
        service = UDPServerService(db_manager=_FakeDB())
        service._mark_tcp_connected("192.168.199.66")

        service._mark_tcp_disconnected("192.168.199.66")

        self.assertEqual(service.count_online_devices(), 0)
        self.assertNotIn("192.168.199.66", service.tcp_connection_counts)
        self.assertNotIn("192.168.199.66", service.devices)

    def test_one_of_multiple_connections_does_not_mark_ip_offline(self):
        service = UDPServerService(db_manager=_FakeDB())
        service._mark_tcp_connected("192.168.199.66")
        service._mark_tcp_connected("192.168.199.66")

        service._mark_tcp_disconnected("192.168.199.66")

        self.assertEqual(service.count_online_devices(), 1)
        self.assertIn("192.168.199.66", service.tcp_connection_counts)


if __name__ == "__main__":
    unittest.main()
