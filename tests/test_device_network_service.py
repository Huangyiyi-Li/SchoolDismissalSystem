import unittest

from src.services.device_network_service import (
    DeviceNetworkProfile,
    DeviceNetworkService,
    parse_device_path_list,
    suggest_device_profile,
)


class _FakeBackend:
    def __init__(self):
        self.is_available = True
        self.availability_reason = ""
        self.last_read_request = None
        self.last_apply_request = None
        self.last_discover_request = None

    def discover_devices(self, listen_port, command_port, exclude_paths=None):
        self.last_discover_request = (listen_port, command_port, list(exclude_paths or []))
        return []

    def read_profile(self, *, current_ip, current_port, device_path):
        self.last_read_request = (current_ip, current_port, device_path)
        return DeviceNetworkProfile(
            local_ip="192.168.1.80",
            subnet_mask="255.255.255.0",
            gateway="192.168.1.1",
            server_ip="192.168.1.10",
            server_port=39169,
            local_port=1000,
        )

    def apply_profile(self, profile, *, current_ip, current_port, device_path):
        self.last_apply_request = (profile, current_ip, current_port, device_path)


class _FakeConfig:
    def __init__(self):
        self.values = {
            "udp_port": 39169,
            "device_network_command_port": 1000,
            "device_network_discovery_port": 51006,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class DeviceNetworkServiceTests(unittest.TestCase):
    def test_parse_device_path_list_reads_nul_separated_values(self):
        raw = b"192.168.1.80:1000\x00192.168.1.81:1000\x00\x00"

        parsed = parse_device_path_list(raw)

        self.assertEqual(parsed, ["192.168.1.80:1000", "192.168.1.81:1000"])

    def test_suggest_device_profile_prefers_current_ip_when_same_subnet(self):
        profile = suggest_device_profile(
            host_ip="192.168.1.10",
            current_ip="192.168.1.80",
            occupied_ips=["192.168.1.80", "192.168.1.81"],
            server_port=39169,
            local_port=1000,
        )

        self.assertEqual(profile.local_ip, "192.168.1.80")
        self.assertEqual(profile.server_ip, "192.168.1.10")
        self.assertEqual(profile.gateway, "192.168.1.1")

    def test_suggest_device_profile_chooses_free_candidate(self):
        profile = suggest_device_profile(
            host_ip="192.168.1.10",
            current_ip="10.0.0.8",
            occupied_ips=["192.168.1.80", "192.168.1.81", "192.168.1.82"],
            server_port=39169,
            local_port=1000,
        )

        self.assertEqual(profile.local_ip, "192.168.1.83")
        self.assertEqual(profile.subnet_mask, "255.255.255.0")

    def test_device_network_service_uses_backend_for_apply(self):
        backend = _FakeBackend()
        service = DeviceNetworkService(_FakeConfig(), backend=backend)
        profile = DeviceNetworkProfile(
            local_ip="192.168.1.88",
            subnet_mask="255.255.255.0",
            gateway="192.168.1.1",
            server_ip="192.168.1.10",
            server_port=39169,
            local_port=1000,
        )

        service.apply_profile(
            profile,
            current_ip="192.168.1.20",
            current_port=1000,
            device_path="192.168.1.20:1000",
        )

        self.assertIsNotNone(backend.last_apply_request)
        self.assertEqual(backend.last_apply_request[0], profile)
        self.assertEqual(backend.last_apply_request[1], "192.168.1.20")
        self.assertEqual(backend.last_apply_request[2], 1000)
        self.assertEqual(backend.last_apply_request[3], "192.168.1.20:1000")

    def test_device_network_service_passes_discovery_and_command_ports(self):
        backend = _FakeBackend()
        service = DeviceNetworkService(_FakeConfig(), backend=backend)

        service.discover_devices()

        self.assertEqual(backend.last_discover_request, (51006, 1000, []))

    def test_device_network_service_passes_excluded_paths(self):
        backend = _FakeBackend()
        service = DeviceNetworkService(_FakeConfig(), backend=backend)

        service.discover_devices(exclude_paths=["192.168.1.80:1000"])

        self.assertEqual(backend.last_discover_request, (51006, 1000, ["192.168.1.80:1000"]))


if __name__ == "__main__":
    unittest.main()
