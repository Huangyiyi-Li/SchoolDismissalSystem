import os
import tempfile
import unittest

from src.services.config_manager import ConfigManager


class LedConfigTests(unittest.TestCase):
    def tearDown(self):
        ConfigManager._instance = None

    def test_led_ip_port_and_page_interval_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "settings.json")
            ConfigManager._instance = None
            config = ConfigManager(path)
            config.set("led_controller_ip", "10.20.30.40")
            config.set("led_controller_port", 5100)
            config.set("led_page_seconds", 8)
            config.set("led_grades_per_page", 6)
            config.set("led_layout_regions", 3)
            config.set("led_width", 640)
            config.set("led_height", 80)
            config.set("led_show_title", False)
            config.set("led_dismissed_delay_seconds", 3)
            config.save()

            ConfigManager._instance = None
            reloaded = ConfigManager(path)

            self.assertEqual(reloaded.get("led_controller_ip"), "10.20.30.40")
            self.assertEqual(reloaded.get("led_controller_port"), 5100)
            self.assertEqual(reloaded.get("led_page_seconds"), 8)
            self.assertEqual(reloaded.get("led_grades_per_page"), 6)
            self.assertEqual(reloaded.get("led_layout_regions"), 3)
            self.assertEqual((reloaded.get("led_width"), reloaded.get("led_height")), (640, 80))
            self.assertFalse(reloaded.get("led_show_title"))
            self.assertEqual(reloaded.get("led_dismissed_delay_seconds"), 3)

    def test_defaults_match_current_bx_6e1xp_installation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ConfigManager._instance = None
            config = ConfigManager(os.path.join(tmpdir, "settings.json"))

            self.assertEqual(config.get("led_controller_ip"), "192.168.100.1")
            self.assertEqual(config.get("led_controller_port"), 5005)
            self.assertEqual((config.get("led_width"), config.get("led_height")), (1024, 96))
            self.assertEqual(config.get("led_grades_per_page"), 2)
            self.assertEqual(config.get("led_layout_regions"), 1)
            self.assertTrue(config.get("led_show_title"))
            self.assertEqual(config.get("led_dismissed_delay_seconds"), 5)


if __name__ == "__main__":
    unittest.main()
