import unittest

from src.services.device_identity import (
    format_device_no_from_node,
    get_or_create_device_no,
    normalize_device_no,
)


class FakeConfig:
    def __init__(self, value=None):
        self.values = {}
        if value is not None:
            self.values["device_no"] = value
        self.saved = False

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.saved = True


class DeviceIdentityTests(unittest.TestCase):
    def test_formats_node_as_12_digit_uppercase_hex_without_colons(self):
        self.assertEqual(format_device_no_from_node(0xAABBCCDDEEFF), "AABBCCDDEEFF")
        self.assertEqual(format_device_no_from_node(0x00000000000A), "00000000000A")

    def test_normalize_removes_common_mac_separators(self):
        self.assertEqual(normalize_device_no("aa:bb:cc:dd:ee:ff"), "AABBCCDDEEFF")
        self.assertEqual(normalize_device_no("aa-bb-cc-dd-ee-ff"), "AABBCCDDEEFF")

    def test_normalize_migrates_old_uuid_getnode_decimal_value(self):
        self.assertEqual(normalize_device_no(str(0xAABBCCDDEEFF)), "AABBCCDDEEFF")

    def test_get_or_create_saves_hex_device_no(self):
        config = FakeConfig()

        device_no = get_or_create_device_no(config, node_getter=lambda: 0xAABBCCDDEEFF)

        self.assertEqual(device_no, "AABBCCDDEEFF")
        self.assertEqual(config.values["device_no"], "AABBCCDDEEFF")
        self.assertTrue(config.saved)


if __name__ == "__main__":
    unittest.main()
