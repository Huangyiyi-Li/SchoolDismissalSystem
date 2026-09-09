import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from src.services import led_renderer as renderer


class LedReviewRegressions(unittest.TestCase):
    def test_missing_and_out_of_order_classes_keep_real_headers_across_grades(self):
        classes = [
            dict(class_id='13', grade_name='一年级', class_name='一年级三班', class_show_name='一(3)班', source_order=0),
            dict(class_id='11', grade_name='一年级', class_name='一年级一班', class_show_name='一(1)班', source_order=1),
            dict(class_id='21', grade_name='二年级', class_name='二年级一班', class_show_name='1班', source_order=2),
        ]
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer, '_draw_centered') as draw:
            renderer.render_led_pages('', classes, {'13':'放学中','21':'已放学'}, directory, show_title=False)
        boxes = {c.args[2]: c.args[1] for c in draw.call_args_list if c.args[2]}
        self.assertIn('3班', boxes)
        self.assertNotIn('2班', boxes)
        self.assertEqual(boxes['3班'][::2], boxes['放学中'][::2])
        self.assertEqual(boxes['1班'][::2], boxes['已放学'][::2])

    def test_named_class_is_not_replaced_with_invented_number(self):
        classes = [dict(class_id='a', grade_name='一年级', class_name='一年级向日葵班', source_order=0)]
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer, '_draw_centered') as draw:
            renderer.render_led_pages('', classes, {}, directory)
        texts = [c.args[2] for c in draw.call_args_list]
        self.assertIn('向日葵班', texts)
        self.assertNotIn('1班', texts)

    def test_dense_status_stays_inside_its_cell(self):
        image = Image.new('1', (80, 60))
        renderer._draw_centered(ImageDraw.Draw(image), (30, 10, 43, 50), '放学中')
        self.assertIsNone(image.crop((0,0,30,60)).getbbox())
        self.assertIsNone(image.crop((43,0,80,60)).getbbox())
        self.assertIsNotNone(image.getbbox())

    def test_club_name_respects_small_requested_font(self):
        image = Image.new('1', (200, 60))
        with patch.object(renderer, '_draw_centered_lines') as draw:
            renderer._draw_centered_club_name(ImageDraw.Draw(image), (0,0,200,60), '足球社团', preferred=5)
        self.assertEqual(draw.call_args.args[3].size, 5)
