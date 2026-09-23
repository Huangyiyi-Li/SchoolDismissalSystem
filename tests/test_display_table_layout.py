from unittest.mock import patch
import pytest
from src.services import led_renderer as r


def catalog():
    return [dict(class_id=f'{g}-{c}', class_type=1, grade_name=grade,
                 class_show_name=f'{g}.{c} 班', source_order=g*10+c)
            for g, grade in [(1, '一年级'), (4, '四年级')] for c in (1, 2, 4)]


def test_custom_grade_pages_override_auto_row_count():
    classes = [dict(class_id=str(g), class_type=1, grade_name=f'{g}年级',
                    class_show_name='1班', source_order=g) for g in range(2, 7)]
    layout = r.build_led_page_layout(classes, grades_per_page=2, regions_per_page=1,
        grade_pages=[['2年级', '3年级'], ['4年级'], ['5年级'], ['6年级']])
    assert [[row.grade_name for row in page.rows] for page in layout.pages] == [
        ['2年级', '3年级'], ['4年级'], ['5年级'], ['6年级']]


def test_custom_grade_pages_create_expected_rotation_files(tmp_path):
    classes = [dict(class_id=str(g), class_type=1, grade_name=f'{g}年级',
                    class_show_name='1班', source_order=g) for g in range(2, 7)]
    pages = r.render_led_pages('', classes, {}, tmp_path, width=1024, height=96,
        show_title=False, grade_pages=[['2年级', '3年级'], ['4年级'], ['5年级'], ['6年级']])
    assert [path.name for path in pages] == [f'led-page-{index:02d}.bmp' for index in range(1, 5)]
    assert all(path.stat().st_size > 0 for path in pages)


def test_narrow_led_title_stacks_characters_instead_of_using_five_pixel_text(tmp_path):
    classes = [dict(class_id=f'{grade}-{number}', class_type=1,
                    grade_name=f'{grade}年级', class_show_name=f'{number}班',
                    source_order=grade * 10 + number)
               for grade in range(1, 7) for number in range(1, 7)]
    metrics = []
    r.render_led_pages('数智家校\n放学系统', classes, {}, tmp_path,
                       width=192, height=96, grades_per_page=6, metrics=metrics)
    assert metrics[0]['title_px'] >= 8
    assert metrics[0]['cell_px'] < 8  # Six columns of full status text are still too dense.


@pytest.mark.parametrize('label,expected', [('1.1 班', '1班'), ('4.4班', '4班'),
    ('４．０４ 班', '4班'), ('四（4）班', '4班'), ('一年级三班', '3班'), ('向日葵班', '向日葵班')])
def test_normalizes_only_recognizable_class_numbers(label, expected):
    assert r._class_header(dict(class_show_name=label, grade_name='一年级')) == expected


def test_grade_class_labels_share_columns_and_keep_status_identity(tmp_path):
    with patch.object(r, '_draw_centered') as draw:
        r.render_led_pages('', catalog(), {(1, '1-1'):'放学中', (1, '4-4'):'已放学'}, tmp_path,
                           width=1366, height=768, show_title=False, color_mode='double')
    boxes = {c.args[2]: c.args[1] for c in draw.call_args_list}
    assert '1.1 班' not in boxes
    assert boxes['1班'][::2] == boxes['放学中'][::2]
    assert boxes['4班'][::2] == boxes['已放学'][::2]
    assert '3班' not in boxes, 'do not invent missing classes'


def capture_layout(tmp_path, **kwargs):
    calls=[]
    original=r._draw_centered
    def capture(draw, box, text, preferred=20, fill=1):
        font=r._fit_font(draw, text, max(1, box[2]-box[0]-4), max(1,box[3]-box[1]-2),preferred)
        calls.append((text,box,font.size))
        return original(draw,box,text,preferred,fill)
    with patch.object(r, '_draw_centered',side_effect=capture):
        r.render_led_pages('',catalog(),{},tmp_path,width=1366,height=768,show_title=False,
                           color_mode='double',**kwargs)
    return calls


def test_table_size_adjustment_keeps_auto_fit_and_changes_actual_font(tmp_path):
    normal = capture_layout(tmp_path / 'normal', table_scale_percent=100)
    smaller = capture_layout(tmp_path / 'smaller', table_scale_percent=70)
    normal_size = next(size for text, _box, size in normal if text == '放学中' or text == '未放学')
    smaller_size = next(size for text, _box, size in smaller if text == '放学中' or text == '未放学')
    assert smaller_size < normal_size


def test_automatic_table_uses_same_actual_font_for_grade_headers_and_status(tmp_path):
    calls=capture_layout(tmp_path)
    assert len({size for text,box,size in calls}) == 1
    assert calls[0][2] > 30, 'PC layout must fit its viewport, not retain the 18 px LED default'


def test_manual_smaller_font_also_shrinks_grade_column(tmp_path):
    large=capture_layout(tmp_path,header_font_size=40,cell_font_size=40)
    small=capture_layout(tmp_path,header_font_size=16,cell_font_size=16)
    def width(calls):
        return next(box[2]-box[0] for text,box,size in calls if text=='一年级')
    assert width(small) < width(large)*0.65


def test_dense_long_named_class_reduces_entire_table_font_consistently(tmp_path):
    items=catalog()
    items.append(dict(class_id='named',class_type=1,grade_name='一年级',class_show_name='向日葵实验班',source_order=99))
    with patch.object(r,'_draw_centered') as draw:
        r.render_led_pages('',items,{},tmp_path,width=320,height=96,show_title=False,color_mode='double')
    assert len({c.kwargs['preferred'] for c in draw.call_args_list})==1
