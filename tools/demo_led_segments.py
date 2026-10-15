"""Generate A/C bitmaps and font metrics without a controller or school data.

Run from the repository root: python -m tools.demo_led_segments OUTPUT_DIR
"""
import argparse
import json
from pathlib import Path

from src.services.led_renderer import render_led_pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--width', type=int, default=416)
    parser.add_argument('--height', type=int, default=240)
    args = parser.parse_args()
    grades = ('一年级', '二年级', '三年级', '四年级', '五年级', '六年级')
    classes = [dict(class_id=f'{g}-{c}', class_type=1, grade_name=grade,
                    class_name=f'{c}班', source_order=g * 100 + c)
               for g, grade in enumerate(grades, 1) for c in range(1, 15)]
    states = ('未放学', '放学中', '已放学')
    statuses = {(1, c['class_id']): states[i % 3] for i, c in enumerate(classes)}
    report = {}
    for mode in ('stacked', 'carousel'):
        metrics = []
        paths = render_led_pages('数智家校 放学系统', classes, statuses,
                                 args.output_dir / mode, width=args.width, height=args.height,
                                 grades_per_page=6, class_layout=mode, classes_per_segment=7,
                                 title_position='top', color_mode='double', metrics=metrics)
        report[mode] = {'pages': len(paths), 'metrics': metrics}
    (args.output_dir / 'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
