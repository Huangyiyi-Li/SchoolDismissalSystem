"""Narrow screens must retain real class identities across blocks and pages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from collections import Counter
from unittest.mock import patch

import pytest
from PIL import Image

from src.services import led_renderer as r
from src.services.config_manager import load_led_setup, validate_led_setup, LedScreenConfig
from tests.test_led_service import FakeConfig, FakeBridge, FakeTimerFactory


def catalog():
    return [dict(class_id=f'{g}-{c}', class_type=1, grade_name=f'{g}年级',
                 class_name=f'{c}班', source_order=g*100+c)
            for g in range(1, 7) for c in range(1, 15)]


@pytest.mark.parametrize('mode,count,regions', [('stacked', 1, 2), ('carousel', 2, 1)])
def test_all_classes_appear_exactly_once_with_correct_segment_headers(mode, count, regions):
    items = catalog()
    layout = r.build_led_page_layout(items, grades_per_page=6,
                                    class_layout=mode, classes_per_segment=7)
    assert len(layout.pages) == count
    assert all(len(p.regions) == regions for p in layout.pages)
    found = [c['class_id'] for p in layout.pages for row in p.rows for c in row.classes]
    assert Counter(found) == Counter(c['class_id'] for c in items)
    headers = [h for p in layout.pages for h in p.region_headers]
    assert headers == [[f'{c}班' for c in range(1, 8)], [f'{c}班' for c in range(8, 15)]]
    assert all(len(rows) == 6 for p in layout.pages for rows in p.regions)


def test_sparse_and_named_classes_do_not_shift_into_another_column():
    items = [dict(class_id=str(i), class_type=1, grade_name=g, class_name=n, source_order=i)
             for i, (g,n) in enumerate([('一年级','10班'), ('一年级','2班'),
                                        ('二年级','2班'), ('二年级','向日葵班')])]
    layout = r.build_led_page_layout(items, grades_per_page=6,
                                    class_layout='stacked', classes_per_segment=2)
    page = layout.pages[0]
    assert page.region_headers == [['2班', '10班'], ['向日葵班']]
    assert [c['class_name'] for c in page.regions[0][1].classes] == ['2班']
    assert page.regions[1][0].classes == []


def test_custom_grade_pages_then_class_segments_cover_every_class():
    layout = r.build_led_page_layout(catalog(), grade_pages=[['3年级','1年级'], ['6年级','2年级','4年级','5年级']],
                                    class_layout='carousel', classes_per_segment=5)
    assert len(layout.pages) == 6
    assert [row.grade_name for row in layout.pages[0].rows] == ['3年级','1年级']
    assert len([c for p in layout.pages for row in p.rows for c in row.classes]) == 84


@pytest.mark.parametrize('mode,page_count', [('stacked',1), ('carousel',2)])
@pytest.mark.parametrize('title_position', ['left','top'])
def test_real_bitmap_has_correct_headers_status_mapping_and_page_label(tmp_path, mode, page_count, title_position):
    metrics=[]
    statuses={(1, c['class_id']): '放学中' if c['class_id']=='1-8' else '已放学' for c in catalog()}
    with patch.object(r, '_draw_centered', wraps=r._draw_centered) as draw:
        paths=r.render_led_pages('学校', catalog(), statuses, tmp_path,
                                 width=416, height=384, grades_per_page=6,
                                 class_layout=mode, classes_per_segment=7,
                                 color_mode='double', title_position=title_position, metrics=metrics)
    assert len(paths)==page_count
    assert all(Image.open(p).size==(416,384) for p in paths)
    assert all(m['column_count']==7 for m in metrics)
    red_status=[c for c in draw.call_args_list if c.args[2]=='放学中']
    assert len(red_status)==1
    box=red_status[0].args[1]
    if mode=='stacked':
        # Top-title rendering draws the table locally, then pastes below its band.
        table_height = 384 - 384//6 if title_position == 'top' else 384
        assert box[1] > table_height//2
    assert '8班' in [c.args[2] for c in draw.call_args_list]
    if mode=='carousel':
        assert metrics[1]['page_label']=='2/2 8班-14班'
        assert any(c.args[2]=='2/2 8班-14班' for c in draw.call_args_list)


@pytest.mark.parametrize('mode,limit', [('invalid',7), ('stacked',0), ('carousel',101),
                                        ('stacked',None), ('carousel',1.5)])
def test_invalid_segment_configuration_rejected(mode, limit):
    screens, plans=load_led_setup(FakeConfig())
    screens[0]['settings'].update(led_class_layout=mode, led_classes_per_segment=limit)
    with pytest.raises(ValueError, match='班级'):
        validate_led_setup(screens,plans)


@pytest.mark.parametrize('mode', ['stacked','carousel'])
def test_empty_catalog_and_last_partial_segment(mode):
    assert not r.build_led_page_layout([], class_layout=mode).pages
    layout=r.build_led_page_layout(catalog(), grades_per_page=6,
                                   class_layout=mode, classes_per_segment=5)
    assert [len(h) for p in layout.pages for h in p.region_headers] == [5,5,4]
    assert len([c for p in layout.pages for row in p.rows for c in row.classes])==84


def test_club_layout_is_unchanged_when_admin_segmentation_enabled():
    clubs=[dict(class_id=str(i),class_type=2,class_name=f'社团{i}',source_order=i) for i in range(9)]
    normal=r.build_led_page_layout(clubs, class_type=2)
    changed=r.build_led_page_layout(clubs, class_type=2, class_layout='stacked', classes_per_segment=1)
    assert normal==changed


def test_impossible_stacked_height_reports_action_instead_of_invalid_cells(tmp_path):
    with pytest.raises(ValueError, match='高度不足.*轮播'):
        r.render_led_pages('', catalog(), {}, tmp_path, width=416, height=64,
                           grades_per_page=6, show_title=False,
                           class_layout='stacked',classes_per_segment=1)


def test_legacy_migration_defaults_to_existing_layout():
    screens,plans=load_led_setup(FakeConfig())
    cfg=LedScreenConfig(FakeConfig(),screens[0],plans[0])
    assert cfg.get('led_class_layout')=='standard'
    assert cfg.get('led_classes_per_segment')==7


def test_runtime_and_desktop_use_saved_segment_configuration(tmp_path):
    from src.database import DatabaseManager
    from src.services.led_service import LedService
    from src.ui.desktop_display import render_desktop_frames
    cfg=FakeConfig({'school_id':'demo', 'led_grades_per_page':6,
                    'led_class_layout':'carousel','led_classes_per_segment':7})
    db=DatabaseManager(str(tmp_path/'demo.db'))
    for c in catalog():
        db.upsert_led_class('demo',1,c['class_id'],c['grade_name'],c['class_name'],source_order=c['source_order'])
    bridge=FakeBridge()
    timers=FakeTimerFactory()
    service=LedService(cfg,db,bridge=bridge,output_dir=tmp_path/'live',timer_factory=timers,
                       submitter=lambda task:task())
    try:
        pages=service._render_pages_for_types({1:catalog()}, {}, tmp_path/'pages')
        assert len(pages)==2
        preview_metrics=[]
        preview=service.render_preview_pages(tmp_path/'preview', 416, 240, 6, 1, False, '',
                                              class_layout='stacked', classes_per_segment=5,
                                              metrics=preview_metrics)
        assert len(preview)==1
        assert preview_metrics[0]['segment_count']==3
        result=service.send_test_screen(width=416,height=240,grades_per_page=6,
                                        class_layout='carousel',classes_per_segment=5)
        assert result.ok
        for _ in range(3):
            timers.timers[-1].fire()
        sent=[call[2][0] for call in bridge.displays]
        assert [p.name for p in sent]==['led-page-01.bmp','led-page-02.bmp','led-page-03.bmp','led-page-01.bmp']
        assert all(Image.open(p).size==(416,240) for p in sent)
        screens,plans=load_led_setup(cfg)
        frames=render_desktop_frames(LedScreenConfig(cfg,screens[0],plans[0]).values,
                                     {1:catalog()}, {}, (640,480))
        assert len(frames)==2
    finally:
        service.shutdown()


def test_settings_segment_values_persist_per_screen_and_reopen():
    from PyQt6.QtWidgets import QApplication
    from tests.test_multi_screen_settings import dialog
    from src.ui.settings_dialog import SettingsDialog
    from tests.test_settings_preview import FakeLedService
    app=QApplication.instance() or QApplication([])
    _,widget=dialog()
    reopened=None
    try:
        widget.led_class_layout_combo.setCurrentIndex(widget.led_class_layout_combo.findData('stacked'))
        widget.led_classes_per_segment_edit.setText('7')
        assert not widget.led_layout_regions_edit.isEnabled()
        widget.screen_panel.add_screen()
        widget.led_class_layout_combo.setCurrentIndex(widget.led_class_layout_combo.findData('carousel'))
        widget.led_classes_per_segment_edit.setText('5')
        with patch('src.ui.settings_dialog.QMessageBox.information'):
            widget.save_settings()
        reopened=SettingsDialog(widget.config,led_service=FakeLedService())
        assert reopened.led_class_layout_combo.currentData()=='stacked'
        reopened.screen_panel.screen_list.setCurrentRow(1)
        assert reopened.led_class_layout_combo.currentData()=='carousel'
        assert reopened.led_classes_per_segment_edit.text()=='5'
    finally:
        if reopened: reopened.close()
        widget.close()
        app.processEvents()
