"""Multi-screen draft editor reusing the existing connection/content/style form."""
from copy import deepcopy
import ipaddress
import uuid
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QListWidget, QLineEdit, QComboBox, QPushButton, QLabel,
                             QMessageBox)
from ..services.config_manager import (load_led_setup, validate_led_setup,
                                       LED_DEVICE_KEYS, LED_PLAN_KEYS, LedScreenConfig)

VALUE_KEYS = {
    'output_type': 'led_output_type', 'monitor': 'led_monitor',
    'title_position': 'led_title_position',
    'ip': 'led_controller_ip', 'port': 'led_controller_port',
    'width': 'led_width', 'height': 'led_height', 'color_mode': 'led_color_mode',
    'page_seconds': 'led_page_seconds', 'grades_per_page': 'led_grades_per_page',
    'regions_per_page': 'led_layout_regions', 'grade_filter_mode': 'led_grade_filter_mode',
    'visible_grades': 'led_visible_grades', 'show_title': 'led_show_title',
    'title': 'led_school_title', 'club_rows_per_group': 'led_club_rows_per_group',
    'club_groups_per_page': 'led_club_groups_per_page',
    'title_font_size': 'led_title_font_size', 'header_font_size': 'led_header_font_size',
    'cell_font_size': 'led_cell_font_size',
}
TEXT_FIELDS = {
    'led_controller_ip': 'led_ip_edit', 'led_controller_port': 'led_port_edit',
    'led_width': 'led_width_edit', 'led_height': 'led_height_edit',
    'led_page_seconds': 'led_page_seconds_edit', 'led_grades_per_page': 'led_grades_per_page_edit',
    'led_layout_regions': 'led_layout_regions_edit', 'led_club_rows_per_group': 'led_club_rows_edit',
    'led_club_groups_per_page': 'led_club_groups_edit',
}


class LedScreenSettings(QWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.screens, self.plans = load_led_setup(dialog.config)
        if not self.screens:
            # Keep one editable disabled entry when an older configuration is empty.
            from ..services.config_manager import ConfigManager
            self.screens = [{'id': uuid.uuid4().hex, 'name': '默认屏幕', 'enabled': False,
                             'plan_id': 'default', 'settings': {}}]
            self.plans = [{'id': 'default', 'name': '默认显示方案', 'settings': {}}]
        self.index = 0
        self.loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        self.screen_list = QListWidget()
        self.screen_list.setMaximumHeight(105)
        layout.addWidget(self.screen_list)
        buttons = QHBoxLayout()
        self.add_button = QPushButton('添加屏幕')
        self.remove_button = QPushButton('移除所选屏幕')
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow('屏幕名称', self.name_edit)
        self.plan_combo = QComboBox()
        form.addRow('显示方案', self.plan_combo)
        self.plan_name = QLineEdit()
        form.addRow('方案名称', self.plan_name)
        layout.addLayout(form)
        self.detach_button = QPushButton('复制为独立方案')
        layout.addWidget(self.detach_button)
        self.scope_hint = QLabel()
        self.scope_hint.setWordWrap(True)
        self.scope_hint.setStyleSheet('color:#526273;font-size:12px;')
        layout.addWidget(self.scope_hint)
        self.screen_list.currentRowChanged.connect(self.select_screen)
        self.plan_combo.currentIndexChanged.connect(self.select_plan)
        self.add_button.clicked.connect(self.add_screen)
        self.remove_button.clicked.connect(self.remove_screen)
        self.detach_button.clicked.connect(self.detach_plan)
        self.reload_lists()
        self.load_form()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_summaries)
        self.status_timer.start(2000)

    def current_plan(self):
        pid = self.screens[self.index]['plan_id']
        return next(plan for plan in self.plans if plan['id'] == pid)

    def update_summaries(self):
        service = self.dialog.led_service
        statuses = service.screen_statuses() if hasattr(service, 'screen_statuses') else {}
        manager = getattr(service, 'desktop_display', None)
        if manager:
            statuses.update(manager.statuses)
        for i, screen in enumerate(self.screens):
            plan = next(p for p in self.plans if p['id'] == screen['plan_id'])
            settings = plan['settings']
            grades = '全部年级' if settings.get('led_grade_filter_mode', 'all') == 'all' else '、'.join(settings.get('led_visible_grades', []))
            status = statuses.get(screen['id'], '未应用')
            if not screen['enabled'] and '失败' not in status:
                status = '未启用'
            self.screen_list.item(i).setText(f"{screen['name']}  ·  {grades}  ·  {status}")

    def reload_lists(self):
        self.loading = True
        self.screen_list.clear()
        self.screen_list.addItems([''] * len(self.screens))
        self.screen_list.setCurrentRow(self.index)
        self.plan_combo.clear()
        for plan in self.plans:
            self.plan_combo.addItem(plan['name'], plan['id'])
        self.plan_combo.setCurrentIndex(self.plan_combo.findData(self.screens[self.index]['plan_id']))
        self.update_summaries()
        self.loading = False

    def store_form(self):
        values = self.dialog._get_led_values()
        if values is None:
            return False
        if not self.name_edit.text().strip() or not self.plan_name.text().strip():
            QMessageBox.warning(self.dialog, '屏幕展示', '请填写屏幕名称和方案名称')
            return False
        screen = self.screens[self.index]
        screen['name'] = self.name_edit.text().strip()
        screen['enabled'] = self.dialog.led_enabled_check.isChecked()
        settings = {VALUE_KEYS[k]: deepcopy(v) for k, v in values.items() if k in VALUE_KEYS}
        screen['settings'] = {k: v for k, v in settings.items() if k in LED_DEVICE_KEYS}
        plan = self.current_plan()
        plan['name'] = self.plan_name.text().strip()
        plan['settings'] = {k: v for k, v in settings.items() if k in LED_PLAN_KEYS}
        return True

    def load_form(self):
        self.loading = True
        self.dialog._desktop_fullscreen_requested = False
        screen, plan = self.screens[self.index], self.current_plan()
        cfg = LedScreenConfig(self.dialog.config, screen, plan)
        self.name_edit.setText(screen['name'])
        self.plan_name.setText(plan['name'])
        self.dialog.led_enabled_check.setChecked(screen['enabled'])
        for key, field in TEXT_FIELDS.items():
            getattr(self.dialog, field).setText(str(cfg.get(key)))
        self.dialog._led_device_drafts = {}
        self.dialog.led_output_combo.blockSignals(True)
        self.dialog.led_output_combo.setCurrentIndex(self.dialog.led_output_combo.findData(cfg.get('led_output_type')))
        self.dialog.led_output_combo.blockSignals(False)
        monitor = cfg.get('led_monitor')
        if self.dialog.led_monitor_combo.findData(monitor) < 0:
            self.dialog.led_monitor_combo.addItem('未连接 · ' + monitor, monitor)
        self.dialog.led_monitor_combo.setCurrentIndex(self.dialog.led_monitor_combo.findData(monitor))
        self.dialog.led_title_position_combo.setCurrentIndex(self.dialog.led_title_position_combo.findData(cfg.get('led_title_position')))
        self.dialog.led_color_mode_combo.setCurrentIndex(self.dialog.led_color_mode_combo.findData(cfg.get('led_color_mode')))
        self.dialog.led_all_grades_check.setChecked(cfg.get('led_grade_filter_mode') == 'all')
        for grade, checkbox in self.dialog.led_grade_checks.items():
            checkbox.setChecked(grade in cfg.get('led_visible_grades'))
        self.dialog.led_show_title_check.setChecked(cfg.get('led_show_title'))
        self.dialog.led_title_edit.setPlainText(cfg.get('led_school_title'))
        for key in ('led_title_font_size', 'led_header_font_size', 'led_cell_font_size'):
            getattr(self.dialog, key + '_spin').setValue(int(cfg.get(key)))
        self.dialog.update_output_controls()
        peers = [s['name'] for s in self.screens if s['plan_id'] == plan['id']]
        self.scope_hint.setText('内容与样式共用于：' + '、'.join(peers) + '。展示方式、显示器、颜色与启用状态只影响当前屏；已放学延迟对全校生效。')
        self.dialog._preview_pages = []
        self.dialog._preview_index = 0
        self.dialog._preview_source_pixmap = None
        self.dialog._preview_state.has_preview = False
        self.dialog._show_preview_message('点击“生成预览”查看当前屏幕效果')
        self.dialog.preview_page_label.setText('0 / 0')
        self.dialog.mark_led_preview_stale()
        self.loading = False

    def select_screen(self, index):
        if self.loading or index < 0 or index == self.index:
            return
        if not self.store_form():
            self.loading = True
            self.screen_list.setCurrentRow(self.index)
            self.loading = False
            return
        self.index = index
        self.reload_lists()
        self.load_form()

    def select_plan(self, index):
        if self.loading or index < 0:
            return
        pid = self.plan_combo.itemData(index)
        if not self.store_form():
            self.reload_lists()
            return
        self.screens[self.index]['plan_id'] = pid
        self.reload_lists()
        self.load_form()

    def add_screen(self):
        if not self.store_form():
            return
        screen = deepcopy(self.screens[self.index])
        screen.update(id=uuid.uuid4().hex, name=f'屏幕 {len(self.screens) + 1}', enabled=False)
        addresses = {s['settings'].get('led_controller_ip') for s in self.screens}
        address = ipaddress.ip_address(screen['settings'].get('led_controller_ip') or '192.168.100.1')
        while str(address) in addresses:
            address += 1
        screen['settings']['led_controller_ip'] = str(address)
        plan = deepcopy(self.current_plan())
        plan.update(id=uuid.uuid4().hex, name=screen['name'] + '显示方案')
        self.plans.append(plan)
        screen['plan_id'] = plan['id']
        self.screens.append(screen)
        self.index = len(self.screens) - 1
        self.reload_lists()
        self.load_form()

    def detach_plan(self):
        if not self.store_form():
            return
        plan = deepcopy(self.current_plan())
        plan.update(id=uuid.uuid4().hex, name=self.screens[self.index]['name'] + '独立方案')
        self.plans.append(plan)
        self.screens[self.index]['plan_id'] = plan['id']
        self.reload_lists()
        self.load_form()

    def remove_screen(self):
        if len(self.screens) == 1:
            QMessageBox.information(self.dialog, '屏幕展示', '最后一块屏可取消“启用此屏”，保留配置方便以后使用。')
            return
        name = self.screens[self.index]['name']
        box = QMessageBox(self.dialog)
        box.setWindowTitle('移除屏幕')
        box.setText(f'保存后移除“{name}”。LED 屏恢复原节目，电脑屏退出展示；班级放学状态将保留。')
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText('移除屏幕')
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.screens.pop(self.index)
        self.index = max(0, self.index - 1)
        self.reload_lists()
        self.load_form()

    def values(self):
        if not self.store_form():
            return None
        used = {screen['plan_id'] for screen in self.screens}
        plans = [plan for plan in self.plans if plan['id'] in used]
        try:
            validate_led_setup(self.screens, plans)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self.dialog, '屏幕展示', str(exc))
            return None
        return deepcopy(self.screens), deepcopy(plans)
