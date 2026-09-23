import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.services.led_renderer import (
    LED_GREEN,
    LED_RED,
    LED_YELLOW,
    build_led_page_layout,
    calculate_club_column_widths,
    display_status,
    render_club_led_pages,
    render_led_pages,
    split_club_name,
)


def make_class(class_id, grade_name, source_order):
    return {
        "class_id": class_id,
        "grade_name": grade_name,
        "class_name": f"{grade_name}{source_order + 1}班",
        "class_show_name": f"{source_order + 1}班",
        "source_order": source_order,
        "class_type": 1,
    }


class LedRendererTests(unittest.TestCase):
    def test_administrative_fonts_use_three_independent_preferred_sizes(self):
        classes = [make_class("101", "一年级", 0)]
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "src.services.led_renderer._draw_title"
        ) as draw_title, patch(
            "src.services.led_renderer._draw_centered"
        ) as draw_centered:
            render_led_pages(
                "健康路小学",
                classes,
                {"101": "放学中"},
                Path(tmpdir),
                title_font_size=28,
                header_font_size=20,
                cell_font_size=16,
            )

        self.assertEqual(draw_title.call_args.kwargs["preferred"], 28)
        preferred_by_text = {
            call.args[2]: call.kwargs["preferred"]
            for call in draw_centered.call_args_list
        }
        self.assertEqual(preferred_by_text["1班"], 20)
        self.assertEqual(preferred_by_text["一年级"], 20)
        self.assertEqual(preferred_by_text["放学中"], 16)

    def test_club_fonts_use_header_size_for_names_and_cell_size_for_status(self):
        clubs = [{
            "class_id": "201",
            "class_type": 2,
            "class_name": "足球社团",
            "class_show_name": "足球社团",
            "source_order": 0,
        }]
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "src.services.led_renderer._draw_centered_club_name"
        ) as draw_name, patch(
            "src.services.led_renderer._draw_centered_single_line"
        ) as draw_single:
            render_club_led_pages(
                "",
                clubs,
                {"201": "已放学"},
                Path(tmpdir),
                show_title=False,
                header_font_size=19,
                cell_font_size=15,
            )

        self.assertEqual(draw_name.call_args.kwargs["preferred"], 19)
        preferred_by_text = {
            call.args[2]: call.kwargs["preferred"]
            for call in draw_single.call_args_list
        }
        self.assertEqual(preferred_by_text["状态"], 19)
        self.assertEqual(preferred_by_text["已放学"], 15)

    def test_status_copy_depends_on_configured_screen_color(self):
        self.assertEqual(display_status("", "single"), "")
        self.assertEqual(display_status("", "double"), "未放学")
        self.assertEqual(display_status("放学中", "double"), "放学中")
        self.assertEqual(display_status("已放学", "double"), "已放学")

    def test_status_copy_can_be_blank_or_custom_without_changing_state(self):
        labels = {"未放学": "", "放学中": "○", "已放学": "已放"}
        self.assertEqual(display_status("", "double", labels), "")
        self.assertEqual(display_status("放学中", "double", labels), "○")
        self.assertEqual(display_status("已放学", "double", labels), "已放")

    def test_custom_status_color_is_used_only_on_dual_color_screen(self):
        from src.services.led_renderer import status_color
        colors = {'未放学': 'red', '放学中': 'green', '已放学': 'yellow'}
        self.assertEqual(status_color('放学中', 'double', colors), (0, 255, 0))
        self.assertEqual(status_color('已放学', 'double', colors), (255, 255, 0))
        self.assertEqual(status_color('放学中', 'single', colors), 1)

    def test_custom_status_text_and_color_reach_rendered_cells(self):
        from src.services import led_renderer as renderer
        classes = [make_class('101', '一年级', 0), make_class('102', '一年级', 1)]
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(renderer, '_draw_centered') as draw:
            renderer.render_led_pages('', classes, {(1, '101'): '放学中', (1, '102'): '已放学'},
                Path(tmpdir), show_title=False, color_mode='double',
                status_labels={'未放学': '', '放学中': '○', '已放学': '●'},
                status_colors={'未放学': 'red', '放学中': 'green', '已放学': 'yellow'})
        cells = {call.args[2]: call.kwargs['fill'] for call in draw.call_args_list}
        self.assertEqual(cells['○'], (0, 255, 0))
        self.assertEqual(cells['●'], (255, 255, 0))

    def test_title_size_percentage_changes_computed_font(self):
        from PIL import ImageDraw
        from src.services import led_renderer as renderer
        image = Image.new('1', (300, 100))
        draw = ImageDraw.Draw(image)
        large = renderer._draw_title(draw, '学校标题', (0, 0, 300, 100), scale_percent=100)
        small = renderer._draw_title(draw, '学校标题', (0, 0, 300, 100), scale_percent=50)
        self.assertLess(small, large)

    def test_dual_color_page_contains_all_three_status_colors(self):
        classes = [
            make_class("101", "一年级", 0),
            make_class("102", "一年级", 1),
            make_class("103", "一年级", 2),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_led_pages(
                "健康路小学",
                classes,
                {"102": "放学中", "103": "已放学"},
                Path(tmpdir),
                color_mode="double",
            )

            with Image.open(pages[0]) as image:
                self.assertEqual(image.mode, "RGB")
                colors = {color for _count, color in image.getcolors(maxcolors=1000000)}
                self.assertIn(LED_RED, colors)
                self.assertIn(LED_YELLOW, colors)
                self.assertIn(LED_GREEN, colors)

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

    def test_last_page_adapts_rows_and_columns_to_uneven_grade_sizes(self):
        classes = []
        source_order = 0
        for grade_name, class_count in (
            ("二年级", 14),
            ("三年级", 14),
            ("七年级", 28),
        ):
            for class_number in range(1, class_count + 1):
                classes.append(
                    {
                        "class_id": f"{grade_name}-{class_number}",
                        "grade_name": grade_name,
                        "class_name": f"{grade_name}{class_number}班",
                        "class_show_name": f"{class_number}班",
                        "source_order": source_order,
                        "class_type": 1,
                    }
                )
                source_order += 1

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "src.services.led_renderer._draw_centered"
        ) as draw_centered:
            pages = render_led_pages(
                "放学系统",
                classes,
                {},
                Path(tmpdir),
                width=1024,
                height=96,
                grades_per_page=2,
                regions_per_page=1,
            )

        boxes_by_text = {}
        for call in draw_centered.call_args_list:
            if call.args[2] in {"二年级", "三年级", "七年级", "14班", "28班"}:
                boxes_by_text.setdefault(call.args[2], []).append(call.args[1])
        self.assertEqual(len(pages), 2)
        second_grade_box = boxes_by_text["二年级"][0]
        seventh_grade_box = boxes_by_text["七年级"][0]
        second_grade_height = second_grade_box[3] - second_grade_box[1]
        seventh_grade_height = seventh_grade_box[3] - seventh_grade_box[1]
        first_page_cell_width = max(
            box[2] - box[0] for box in boxes_by_text["14班"]
        )
        second_page_cell_width = boxes_by_text["28班"][0][2] - boxes_by_text["28班"][0][0]
        self.assertGreater(seventh_grade_height, second_grade_height)
        self.assertGreater(first_page_cell_width, second_page_cell_width)

    def test_three_horizontal_regions_place_six_grades_on_one_page(self):
        classes = [make_class(str(index), f"{index}年级", index) for index in range(1, 7)]

        layout = build_led_page_layout(
            classes,
            grades_per_page=2,
            regions_per_page=3,
        )

        self.assertEqual(len(layout.pages), 1)
        self.assertEqual(
            [[row.grade_name for row in region] for region in layout.pages[0].regions],
            [["1年级", "2年级"], ["3年级", "4年级"], ["5年级", "6年级"]],
        )

    def test_empty_trailing_region_does_not_draw_fake_class_header(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "src.services.led_renderer._draw_centered"
        ) as draw_centered:
            render_led_pages(
                "放学系统",
                [make_class("101", "一年级", 0)],
                {},
                Path(tmpdir),
                grades_per_page=1,
                regions_per_page=2,
            )

        header_calls = [
            call for call in draw_centered.call_args_list if call.args[2] == "1班"
        ]
        self.assertEqual(len(header_calls), 1)

    def test_club_classes_render_as_named_rows_with_status_column(self):
        clubs = [
            {
                "class_id": "201",
                "class_type": 2,
                "class_name": "足球社团",
                "class_show_name": "足球社团",
                "source_order": 0,
            },
            {
                "class_id": "202",
                "class_type": 2,
                "class_name": "合唱社团",
                "class_show_name": "合唱社团",
                "source_order": 1,
            },
        ]

        layout = build_led_page_layout(
            clubs,
            grades_per_page=2,
            regions_per_page=1,
            class_type=2,
        )

        self.assertEqual(
            [row.grade_name for row in layout.pages[0].rows],
            ["足球社团", "合唱社团"],
        )

    def test_club_layout_uses_custom_groups_and_rows(self):
        clubs = [
            {
                "class_id": str(200 + index),
                "class_type": 2,
                "class_name": f"社团{index + 1}",
                "class_show_name": f"社团{index + 1}",
                "source_order": index,
            }
            for index in range(50)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_club_led_pages(
                "",
                clubs,
                {},
                Path(tmpdir),
                width=1024,
                height=96,
                rows_per_group=4,
                groups_per_page=5,
                show_title=False,
            )

            self.assertEqual(len(pages), 3)
            for page in pages:
                with Image.open(page) as image:
                    self.assertEqual(image.size, (1024, 96))
                    self.assertEqual(image.mode, "1")

    def test_club_status_column_reserves_three_character_single_line_width(self):
        name_width, status_width = calculate_club_column_widths(204)

        self.assertEqual((name_width, status_width), (118, 86))
        self.assertGreater(status_width, 3 * 12)

    def test_long_club_name_splits_into_at_most_two_balanced_lines(self):
        lines = split_club_name("青少年科技创新社团")

        self.assertEqual("".join(lines), "青少年科技创新社团")
        self.assertEqual(len(lines), 2)
        self.assertLessEqual(abs(len(lines[0]) - len(lines[1])), 1)

    def test_short_name_can_also_wrap_when_the_cell_is_narrow(self):
        lines = split_club_name("科技社团")

        self.assertEqual(lines, ["科技", "社团"])

    def test_title_can_be_disabled_and_custom_pixel_size_is_used(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_led_pages(
                "",
                [make_class("101", "一年级", 0)],
                {"101": "放学中"},
                Path(tmpdir),
                width=640,
                height=80,
                show_title=False,
            )

            with Image.open(pages[0]) as image:
                self.assertEqual(image.size, (640, 80))

    def test_narrow_screen_keeps_layout_coordinates_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_led_pages(
                "学校\n放学系统",
                [
                    make_class("101", "一年级", 0),
                    make_class("201", "二年级", 1),
                ],
                {},
                Path(tmpdir),
                width=96,
                height=32,
                grades_per_page=1,
                regions_per_page=2,
                show_title=True,
            )

            self.assertEqual(len(pages), 1)
            with Image.open(pages[0]) as image:
                self.assertEqual(image.size, (96, 32))


if __name__ == "__main__":
    unittest.main()
