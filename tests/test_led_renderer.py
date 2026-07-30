import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.services.led_renderer import build_led_page_layout, render_led_pages


def make_class(class_id, grade_name, source_order):
    return {
        "class_id": class_id,
        "grade_name": grade_name,
        "class_name": f"{grade_name}{source_order + 1}班",
        "class_show_name": f"{source_order + 1}班",
        "source_order": source_order,
    }


class LedRendererTests(unittest.TestCase):
    def test_layout_uses_global_maximum_without_fabricating_classes(self):
        classes = [
            make_class("101", "一年级", 0),
            make_class("102", "一年级", 1),
            make_class("201", "二年级", 2),
        ]

        layout = build_led_page_layout(classes, grades_per_page=2)

        self.assertEqual(layout.max_columns, 2)
        self.assertEqual(len(layout.pages), 1)
        self.assertEqual([len(row.classes) for row in layout.pages[0].rows], [2, 1])
        self.assertEqual(layout.pages[0].rows[1].classes[0]["class_id"], "201")

    def test_five_grades_render_three_monochrome_1024_by_96_pages(self):
        classes = [make_class(str(index), f"{index}年级", 0) for index in range(1, 6)]

        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_led_pages(
                "健康路小学",
                classes,
                {"1": "放学中", "2": "已放学"},
                Path(tmpdir),
                width=1024,
                height=96,
                grades_per_page=2,
            )

            self.assertEqual(len(pages), 3)
            for page in pages:
                with Image.open(page) as image:
                    self.assertEqual(image.size, (1024, 96))
                    self.assertEqual(image.mode, "1")


if __name__ == "__main__":
    unittest.main()
