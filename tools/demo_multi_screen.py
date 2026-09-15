"""Isolated two-screen demo: renders real pages, never contacts physical devices."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--screenshot', type=Path)
args = parser.parse_args()
if args.screenshot:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from src.database import DatabaseManager
from src.services.config_manager import ConfigManager
from src.services.led_service import MultiScreenLedService
from src.services.led_bridge_client import BridgeResult
from src.ui.settings_dialog import SettingsDialog


class DemoBridge:
    def __init__(self):
        self.page = None
        self.online = True

    def ping(self, *args):
        return BridgeResult(self.online, '模拟连接正常' if self.online else '模拟断线')

    def display(self, ip, port, pages, **kwargs):
        if not self.online:
            return BridgeResult(False, '模拟屏幕断线')
        self.page = pages[0]
        return BridgeResult(True, '模拟画面已更新')

    def clear(self, *args):
        if not self.online:
            return BridgeResult(False, '模拟屏幕断线')
        self.page = None
        return BridgeResult(True, '模拟恢复原节目')


app = QApplication([])
with tempfile.TemporaryDirectory(prefix='dismissal-multi-screen-demo-') as temp:
    root = Path(temp)
    config = ConfigManager(str(root / 'settings.json'))
    config.set('school_id', 'demo')
    config.set('led_enabled', True)
    config.set('led_screens', [
        {'id': 'south', 'name': '南门屏', 'enabled': True, 'plan_id': 'low', 'settings': {'led_controller_ip': '192.0.2.1', 'led_width': 640, 'led_height': 128}},
        {'id': 'north', 'name': '北门屏', 'enabled': True, 'plan_id': 'high', 'settings': {'led_controller_ip': '192.0.2.2', 'led_width': 640, 'led_height': 128}},
    ])
    config.set('led_display_plans', [
        {'id': 'low', 'name': '一、二年级', 'settings': {'led_grade_filter_mode': 'selected', 'led_visible_grades': ['一年级', '二年级'], 'led_show_title': False}},
        {'id': 'high', 'name': '三、四年级', 'settings': {'led_grade_filter_mode': 'selected', 'led_visible_grades': ['三年级', '四年级'], 'led_show_title': False}},
    ])
    db = DatabaseManager(str(root / 'demo.db'))
    for number, grade in enumerate(['一年级', '二年级', '三年级', '四年级'], 1):
        for room in range(1, 4):
            db.upsert_led_class('demo', 1, f'{number}{room}', grade, f'{grade}{room}班', source_order=number * 10 + room)
    bridges = {}
    def make_bridge(screen):
        bridge = DemoBridge()
        bridges[screen['id']] = bridge
        return bridge
    service = MultiScreenLedService(config, db, bridge_factory=make_bridge, output_dir=root / 'pages')
    window = QWidget()
    window.setWindowTitle('多屏模拟演示 · 不连接真实设备')
    window.resize(1000, 610)
    window.setStyleSheet('QWidget {font-size:14px;} QPushButton {padding:8px;}')
    layout = QVBoxLayout(window)
    heading = QLabel('双屏放学展示')
    heading.setStyleSheet('font-size:25px;font-weight:bold;')
    layout.addWidget(heading)
    layout.addWidget(QLabel('合成演示数据 · 临时配置与数据库 · 不播报、不推送、不连接真实屏幕'))
    actions = QHBoxLayout()
    for grade in (1, 3):
        button = QPushButton(f'模拟{grade}年级 1 班刷卡')
        button.clicked.connect(lambda checked=False, grade=grade: service.mark_dismissing(f'{grade}1'))
        actions.addWidget(button)
    shared = QPushButton('两屏改为相同内容')
    def toggle_shared():
        screen = config.get('led_screens')[1]
        screen['plan_id'] = 'high' if screen['plan_id'] == 'low' else 'low'
        shared.setText('两屏改为不同内容' if screen['plan_id'] == 'low' else '两屏改为相同内容')
        service.reconfigure()
    shared.clicked.connect(toggle_shared)
    actions.addWidget(shared)
    offline = QPushButton('模拟北门屏断线')
    def toggle_offline():
        bridges['north'].online = not bridges['north'].online
        offline.setText('恢复北门屏连接' if not bridges['north'].online else '模拟北门屏断线')
        service.refresh_async()
    offline.clicked.connect(toggle_offline)
    actions.addWidget(offline)
    layout.addLayout(actions)
    labels = {}
    titles = {}
    for sid in ('south', 'north'):
        titles[sid] = QLabel()
        layout.addWidget(titles[sid])
        label = QLabel('等待画面')
        label.setMinimumHeight(145)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet('background:black;color:white;')
        layout.addWidget(label)
        labels[sid] = label
    settings = QPushButton('打开多屏设置')
    def open_settings():
        dialog = SettingsDialog(config, led_service=service, parent=window)
        dialog.navigation.setCurrentRow(3)
        dialog.exec()
    settings.clicked.connect(open_settings)
    layout.addWidget(settings)
    def update():
        status = service.screen_statuses()
        for sid, label in labels.items():
            screen = next((s for s in config.get('led_screens') if s['id'] == sid), None)
            if screen is None:
                titles[sid].setText('已移除')
                label.clear()
                continue
            plan = next(p for p in config.get('led_display_plans') if p['id'] == screen['plan_id'])
            titles[sid].setText(screen['name'] + ' · ' + plan['name'] + ' · ' + status.get(sid, ''))
            page = bridges[sid].page
            if page and Path(page).exists():
                label.setPixmap(QPixmap(str(page)).scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                label.setText('模拟原节目')
        service.set_dismissal_active(True, {1})
    timer = QTimer(window)
    timer.timeout.connect(update)
    timer.start(250)
    service.mark_dismissing('11')
    service.mark_dismissing('31')
    window.show()
    if args.screenshot:
        def capture():
            update()
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(900, capture)
    app.exec()
    service.shutdown()
    # Let independent output tasks release temporary image/database files.
    for output in service.outputs.values():
        if output._executor:
            output._executor.shutdown(wait=True)
