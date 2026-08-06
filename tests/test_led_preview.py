import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.services.led_preview import colorize_led_preview, scaled_preview_size


class LedPreviewTests(unittest.TestCase):
    def test_monochrome_led_bitmap_is_tinted_red_for_local_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "page.bmp"
            image = Image.new("1", (2, 1), 0)
            image.putpixel((1, 0), 1)
            image.save(source)

            preview = colorize_led_preview(source)

            self.assertEqual(preview.getpixel((0, 0)), (5, 0, 0))
            self.assertEqual(preview.getpixel((1, 0)), (255, 48, 32))

    def test_preview_zoom_preserves_led_aspect_ratio(self):
        self.assertEqual(scaled_preview_size(1024, 96, 100), (1024, 96))
        self.assertEqual(scaled_preview_size(1024, 96, 200), (2048, 192))

    def test_dual_color_preview_preserves_red_yellow_and_green_pixels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "dual.bmp"
            image = Image.new("RGB", (3, 1))
            image.putdata([(255, 0, 0), (255, 255, 0), (0, 255, 0)])
            image.save(source)

            preview = colorize_led_preview(source, color_mode="double")

            self.assertEqual(
                list(preview.getdata()),
                [(255, 0, 0), (255, 255, 0), (0, 255, 0)],
            )


if __name__ == "__main__":
    unittest.main()
