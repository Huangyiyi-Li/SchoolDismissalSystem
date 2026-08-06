import unittest

from src.services.led_dimensions import validate_led_dimensions


class LedDimensionTests(unittest.TestCase):
    def test_non_multiple_pixel_dimensions_are_allowed(self):
        result = validate_led_dimensions("1001", "97")

        self.assertTrue(result.ok)
        self.assertEqual((result.width, result.height), (1001, 97))

    def test_dimensions_must_be_positive_integers(self):
        self.assertEqual(
            validate_led_dimensions("1024.5", "96").message,
            "像素宽度和高度必须填写正整数",
        )
        self.assertEqual(
            validate_led_dimensions("0", "96").message,
            "像素宽度和高度必须大于 0",
        )

    def test_bx_6e1xp_width_height_and_total_limits_are_reported_separately(self):
        self.assertEqual(
            validate_led_dimensions("2049", "96").message,
            "BX-6E1XP 单色屏宽度不能超过 2048 像素",
        )
        self.assertEqual(
            validate_led_dimensions("1024", "1025").message,
            "BX-6E1XP 屏幕高度不能超过 1024 像素",
        )
        self.assertEqual(
            validate_led_dimensions("1024", "600").message,
            "BX-6E1XP 单色屏总像素不能超过 524288（512K）",
        )

    def test_dual_color_uses_official_256k_pixel_limit(self):
        self.assertTrue(validate_led_dimensions("1024", "96", "double").ok)
        self.assertEqual(
            validate_led_dimensions("1024", "300", "double").message,
            "BX-6E1XP 双色屏总像素不能超过 262144（256K）",
        )


if __name__ == "__main__":
    unittest.main()
