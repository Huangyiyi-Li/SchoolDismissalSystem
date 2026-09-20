"""Generate reproducible local screenshots with synthetic classes; no devices/network."""
import argparse
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PyQt6.QtWidgets import QApplication
from src.services.config_manager import ConfigManager
from src.services.led_renderer import render_led_pages
from src.ui.desktop_display import render_desktop_frames
from src.ui.settings_dialog import SettingsDialog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='docs/desktop-display/examples')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    values = dict(ConfigManager.DEFAULT_CONFIG, led_school_title='示例小学 · 放学信息',
                  led_color_mode='double', led_title_position='top', led_grades_per_page=6)
    classes = {1: [{'class_id': f'{grade}-{room}', 'class_type': 1,
                    'grade_name': f'{"一二三四五六"[grade-1]}年级', 'class_name': f'{room}班',
                    'class_show_name': f'{grade}.{room} 班',
                    'source_order': grade * 10 + room} for grade in range(1, 7) for room in range(1, 9)]}
    statuses = {(1, item['class_id']): ('已放学' if i < 16 else '放学中')
                for i, item in enumerate(classes[1]) if i < 21}
    for name, size, position in [('pc-top-1920x1080', (1920, 1080), 'top'),
                                  ('pc-left-1366x768', (1366, 768), 'left'),
                                  ('pc-top-portrait', (768, 1366), 'top')]:
        values['led_title_position'] = position
        values['led_school_title'] = '示例小学\n放学信息' if position == 'left' else '示例小学 · 放学信息'
        w, h, data = render_desktop_frames(values, classes, statuses, size)[0]
        Image.frombytes('RGB', (w, h), data).save(output / (name + '.png'))
    dense = {1: [dict(class_id=f'{g}-{c}', class_type=1, grade_name=f'{"一二三四五六"[g-1]}年级',
                       class_show_name=f'{g}.{c} 班', source_order=g*100+c)
                 for g in range(1, 7) for c in range(1, 15)]}
    values['led_title_position'] = 'top'
    w, h, data = render_desktop_frames(values, dense, statuses, (1920, 1080))[0]
    Image.frombytes('RGB', (w, h), data).save(output / 'pc-top-14-classes.png')
    paths = render_led_pages('示例小学 · 放学信息', classes[1], statuses, output / 'led',
                             width=1024, height=96, title_position='top', color_mode='double')
    with Image.open(paths[0]) as image:
        image.save(output / 'led-top-1024x96.png')
    app = QApplication.instance() or QApplication([])
    class Config:
        def get(self, key, default=None):
            return dict(values, school_id='demo').get(key, default)
    dialog = SettingsDialog(Config())
    dialog.navigation.setCurrentRow(3)
    dialog.led_output_combo.setCurrentIndex(1)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / 'settings-pc-device.png'))
    dialog.led_tabs.setCurrentIndex(2)
    dialog.led_title_position_combo.setCurrentIndex(1)
    app.processEvents()
    dialog.grab().save(str(output / 'settings-title-position.png'))
    dialog.close()
    print(f'Wrote synthetic previews to {output.resolve()}')


if __name__ == '__main__':
    main()
