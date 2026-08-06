from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QFormLayout,
                             QCheckBox, QPlainTextEdit, QGroupBox, QWidget,
                             QScrollArea, QFrame, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from ..services.device_identity import format_device_no_from_node, normalize_device_no
from ..services.led_dimensions import validate_led_dimensions
from ..services.led_preview import (
    PreviewRefreshState,
    colorize_led_preview,
    scaled_preview_size,
)
from ..utils.path_utils import get_app_root
import ipaddress
import threading
import uuid
from io import BytesIO
from pathlib import Path

class SettingsDialog(QDialog):
    led_action_finished = pyqtSignal(bool, str)
    preview_finished = pyqtSignal(object)

    def __init__(
        self,
        config_manager,
        data_sync_service=None,
        led_service=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config_manager
        self.sync_service = data_sync_service
        self.led_service = led_service
        self._led_action_running = False
        self._closing = False
        self.setWindowTitle("绑定学校")
        self.resize(1120, 720)
        self._preview_pages = []
        self._preview_index = 0
        self._preview_source_pixmap = None
        self._preview_zoom_percent = 100
        self._preview_fit_to_window = False
        self._preview_color_mode = "single"
        self._led_validation_message = ""
        self._preview_state = PreviewRefreshState()
        self.led_action_finished.connect(self._show_led_result)
        self.preview_finished.connect(self._handle_preview_finished)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        form_layout = QFormLayout()
        
        # School ID
        self.school_id_edit = QLineEdit()
        self.school_id_edit.setText(self.config.get("school_id", ""))
        self.school_id_edit.setPlaceholderText("请输入学校ID (如 40125)")
        form_layout.addRow("学校 ID:", self.school_id_edit)

        self.api_base_url_edit = QLineEdit()
        self.api_base_url_edit.setText(self.config.get("api_base_url", "https://rest.xxt.cn"))
        self.api_base_url_edit.setPlaceholderText("https://rest.xxt.cn 或 https://rest-test.xxt.cn")
        form_layout.addRow("接口地址:", self.api_base_url_edit)

        self.device_no_edit = QLineEdit()
        self.device_no_edit.setText(normalize_device_no(self.config.get("device_no", "")))
        self.device_no_edit.setPlaceholderText("12位十六进制设备编号，如 AABBCCDDEEFF")
        device_no_layout = QHBoxLayout()
        device_no_layout.addWidget(self.device_no_edit)
        generate_device_no_btn = QPushButton("一键获取")
        generate_device_no_btn.clicked.connect(self.fill_local_device_no)
        device_no_layout.addWidget(generate_device_no_btn)
        form_layout.addRow("设备编号:", device_no_layout)

        self.mqtt_enabled_check = QCheckBox("启用 MQTT 心跳/指令")
        self.mqtt_enabled_check.setChecked(self.config.get("mqtt_enabled", True))
        form_layout.addRow("MQTT:", self.mqtt_enabled_check)
        
        # UDP Port
        self.port_edit = QLineEdit()
        self.port_edit.setText(str(self.config.get("udp_port", 39169)))
        form_layout.addRow("UDP 端口:", self.port_edit)

        # Removed manual time settings as per requirement
        # Time is now managed via Server Schedule

        left_layout.addLayout(form_layout)

        led_group = QGroupBox("LED 屏（仰邦 BX-6E1XP）")
        led_form = QFormLayout(led_group)
        self.led_enabled_check = QCheckBox("启用 LED 状态屏")
        self.led_enabled_check.setChecked(self.config.get("led_enabled", False))
        led_form.addRow("状态:", self.led_enabled_check)

        self.led_ip_edit = QLineEdit(
            self.config.get("led_controller_ip", "192.168.100.1")
        )
        self.led_ip_edit.setPlaceholderText("192.168.100.1")
        led_form.addRow("控制卡 IP:", self.led_ip_edit)

        self.led_port_edit = QLineEdit(
            str(self.config.get("led_controller_port", 5005))
        )
        led_form.addRow("控制卡端口:", self.led_port_edit)

        self.led_color_mode_combo = QComboBox()
        self.led_color_mode_combo.addItem("单色", "single")
        self.led_color_mode_combo.addItem("双色", "double")
        saved_color_mode = self.config.get("led_color_mode", "single")
        saved_color_index = self.led_color_mode_combo.findData(saved_color_mode)
        self.led_color_mode_combo.setCurrentIndex(max(0, saved_color_index))
        led_form.addRow("屏幕颜色:", self.led_color_mode_combo)
        self.led_color_hint = QLabel()
        self.led_color_hint.setWordWrap(True)
        self.led_color_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        led_form.addRow("", self.led_color_hint)
        self.led_color_mode_combo.currentIndexChanged.connect(
            self._update_led_color_hint
        )
        self._update_led_color_hint()

        size_layout = QHBoxLayout()
        self.led_width_edit = QLineEdit(str(self.config.get("led_width", 1024)))
        self.led_width_edit.setPlaceholderText("宽，如 1024")
        self.led_height_edit = QLineEdit(str(self.config.get("led_height", 96)))
        self.led_height_edit.setPlaceholderText("高，如 96")
        size_layout.addWidget(self.led_width_edit)
        size_layout.addWidget(QLabel("×"))
        size_layout.addWidget(self.led_height_edit)
        led_form.addRow("像素尺寸:", size_layout)
        self.led_size_hint = QLabel()
        self.led_size_hint.setWordWrap(True)
        self.led_size_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        led_form.addRow("", self.led_size_hint)
        self._update_led_size_hint()

        self.led_page_seconds_edit = QLineEdit(
            str(self.config.get("led_page_seconds", 5))
        )
        self.led_page_seconds_edit.setPlaceholderText("每页停留秒数")
        led_form.addRow("翻页间隔(秒):", self.led_page_seconds_edit)

        self.led_grades_per_page_edit = QLineEdit(
            str(self.config.get("led_grades_per_page", 2))
        )
        self.led_grades_per_page_edit.setPlaceholderText("行政班每区显示 1-6 个年级")
        led_form.addRow("行政班每区行数:", self.led_grades_per_page_edit)

        self.led_layout_regions_edit = QLineEdit(
            str(self.config.get("led_layout_regions", 1))
        )
        self.led_layout_regions_edit.setPlaceholderText("行政班横向分区数 1-6")
        led_form.addRow("行政班横向分区:", self.led_layout_regions_edit)

        self.led_club_rows_edit = QLineEdit(
            str(self.config.get("led_club_rows_per_group", 4))
        )
        self.led_club_rows_edit.setPlaceholderText("每组显示 1-6 个社团")
        led_form.addRow("社团班每组行数:", self.led_club_rows_edit)

        self.led_club_groups_edit = QLineEdit(
            str(self.config.get("led_club_groups_per_page", 5))
        )
        self.led_club_groups_edit.setPlaceholderText("每页横向组数 1-6")
        led_form.addRow("社团班横向组数:", self.led_club_groups_edit)
        club_layout_hint = QLabel(
            "社团班每页容量 = 横向组数 × 每组行数；状态固定单行，长名称自动缩小并最多分两行。"
        )
        club_layout_hint.setWordWrap(True)
        club_layout_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        led_form.addRow("", club_layout_hint)

        self.led_dismissed_delay_edit = QLineEdit(
            str(self.config.get("led_dismissed_delay_seconds", 5))
        )
        self.led_dismissed_delay_edit.setPlaceholderText("放学中变为已放学的秒数")
        led_form.addRow("已放学延迟(秒):", self.led_dismissed_delay_edit)

        self.led_show_title_check = QCheckBox("显示左侧标题")
        self.led_show_title_check.setChecked(self.config.get("led_show_title", True))
        led_form.addRow("标题区域:", self.led_show_title_check)

        self.led_title_edit = QPlainTextEdit()
        self.led_title_edit.setPlainText(
            self.config.get("led_school_title", "数智家校\n放学系统")
        )
        self.led_title_edit.setMaximumHeight(72)
        self.led_title_edit.setPlaceholderText("学校名称\n数智家校\n放学系统")
        self.led_title_edit.setEnabled(self.led_show_title_check.isChecked())
        self.led_show_title_check.toggled.connect(self.led_title_edit.setEnabled)
        led_form.addRow("左侧标题:", self.led_title_edit)

        led_test_layout = QHBoxLayout()
        self.led_connect_btn = QPushButton("测试连接")
        self.led_connect_btn.clicked.connect(self.test_led_connection)
        led_test_layout.addWidget(self.led_connect_btn)
        self.led_screen_btn = QPushButton("发送测试画面")
        self.led_screen_btn.clicked.connect(self.test_led_screen)
        led_test_layout.addWidget(self.led_screen_btn)
        self.led_restore_btn = QPushButton("清空状态/恢复原节目")
        self.led_restore_btn.clicked.connect(self.reset_led_screen)
        led_test_layout.addWidget(self.led_restore_btn)
        led_form.addRow("设备测试:", led_test_layout)
        left_layout.addWidget(led_group)

        # Buttons
        btn_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        if self.sync_service:
            sync_btn = QPushButton("立即同步数据")
            sync_btn.clicked.connect(self.trigger_sync)
            btn_layout.addWidget(sync_btn)

        left_layout.addLayout(btn_layout)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setWidget(left_widget)
        layout.addWidget(left_scroll, stretch=4)

        preview_group = QGroupBox("LED 内容预览（本地预览，不会发送到控制卡）")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("点击“生成预览”查看当前参数效果")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.resize(560, 260)
        self.preview_label.setStyleSheet(
            "background:#050000;color:#d1d5db;"
        )
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setMinimumSize(560, 260)
        self.preview_scroll.setStyleSheet(
            "QScrollArea{background:#050000;border:1px solid #374151;}"
            "QScrollBar{background:#1f2937;}"
        )
        self.preview_scroll.setWidget(self.preview_label)
        preview_layout.addWidget(self.preview_scroll, stretch=1)
        self.preview_status_label = QLabel("")
        self.preview_status_label.setWordWrap(True)
        self.preview_status_label.setStyleSheet("color:#6b7280;")
        preview_layout.addWidget(self.preview_status_label)

        preview_controls = QHBoxLayout()
        self.preview_generate_btn = QPushButton("生成预览")
        self.preview_generate_btn.clicked.connect(self.generate_led_preview)
        preview_controls.addWidget(self.preview_generate_btn)
        self.preview_prev_btn = QPushButton("上一页")
        self.preview_prev_btn.clicked.connect(self.show_previous_preview_page)
        preview_controls.addWidget(self.preview_prev_btn)
        self.preview_page_label = QLabel("0 / 0")
        self.preview_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_controls.addWidget(self.preview_page_label, stretch=1)
        self.preview_next_btn = QPushButton("下一页")
        self.preview_next_btn.clicked.connect(self.show_next_preview_page)
        preview_controls.addWidget(self.preview_next_btn)
        preview_layout.addLayout(preview_controls)

        zoom_controls = QHBoxLayout()
        zoom_controls.addWidget(QLabel("预览缩放:"))
        self.preview_zoom_out_btn = QPushButton("－")
        self.preview_zoom_out_btn.setToolTip("缩小预览")
        self.preview_zoom_out_btn.clicked.connect(self.zoom_preview_out)
        zoom_controls.addWidget(self.preview_zoom_out_btn)
        self.preview_zoom_label = QLabel("100%")
        self.preview_zoom_label.setMinimumWidth(48)
        self.preview_zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_controls.addWidget(self.preview_zoom_label)
        self.preview_zoom_in_btn = QPushButton("＋")
        self.preview_zoom_in_btn.setToolTip("放大预览")
        self.preview_zoom_in_btn.clicked.connect(self.zoom_preview_in)
        zoom_controls.addWidget(self.preview_zoom_in_btn)
        self.preview_actual_size_btn = QPushButton("100%")
        self.preview_actual_size_btn.setToolTip("一个图片像素对应一个屏幕像素")
        self.preview_actual_size_btn.clicked.connect(self.reset_preview_zoom)
        zoom_controls.addWidget(self.preview_actual_size_btn)
        self.preview_fit_btn = QPushButton("适应窗口")
        self.preview_fit_btn.clicked.connect(self.fit_preview_to_window)
        zoom_controls.addWidget(self.preview_fit_btn)
        zoom_controls.addStretch(1)
        preview_layout.addLayout(zoom_controls)

        self.preview_sample_check = QCheckBox("使用示例状态预览")
        self.preview_sample_check.setChecked(True)
        self.preview_sample_check.toggled.connect(self.mark_led_preview_stale)
        preview_layout.addWidget(self.preview_sample_check)
        layout.addWidget(preview_group, stretch=6)

        for editor in (
            self.led_width_edit,
            self.led_height_edit,
            self.led_grades_per_page_edit,
            self.led_layout_regions_edit,
            self.led_club_rows_edit,
            self.led_club_groups_edit,
            self.led_title_edit,
        ):
            if isinstance(editor, QPlainTextEdit):
                editor.textChanged.connect(self.mark_led_preview_stale)
            else:
                editor.textChanged.connect(self.mark_led_preview_stale)
        self.led_show_title_check.toggled.connect(self.mark_led_preview_stale)
        self.led_color_mode_combo.currentIndexChanged.connect(
            self.mark_led_preview_stale
        )
        self._update_preview_buttons()

    def save_settings(self):
        new_school_id = self.school_id_edit.text().strip()
        api_base_url = self.api_base_url_edit.text().strip().rstrip("/")
        device_no = normalize_device_no(self.device_no_edit.text())
        port_str = self.port_edit.text().strip()

        if not new_school_id:
            QMessageBox.warning(self, "错误", "学校 ID 不能为空")
            return

        try:
            port = int(port_str)
        except ValueError:
            QMessageBox.warning(self, "错误", "UDP 端口必须是数字")
            return

        led_values = self._get_led_values()
        if led_values is None:
            return

        # Check if School ID changed
        old_school_id = self.config.get("school_id")
        old_api_base_url = self.config.get("api_base_url", "https://rest.xxt.cn")
        old_led_enabled = bool(self.config.get("led_enabled", False))
        old_led_ip = self.config.get("led_controller_ip", "192.168.100.1")
        old_led_port = int(self.config.get("led_controller_port", 5005))
        old_led_color_mode = self.config.get("led_color_mode", "single")
        school_id_changed = new_school_id != old_school_id
        api_base_url_changed = (api_base_url or "https://rest.xxt.cn") != old_api_base_url
        led_target_changed = (
            led_values["ip"] != old_led_ip
            or led_values["port"] != old_led_port
            or led_values["color_mode"] != old_led_color_mode
        )
        new_led_enabled = self.led_enabled_check.isChecked()

        self.config.set("school_id", new_school_id)
        self.config.set("api_base_url", api_base_url or "https://rest.xxt.cn")
        self.config.set("device_no", device_no)
        self.config.set("mqtt_enabled", self.mqtt_enabled_check.isChecked())
        self.config.set("udp_port", port)
        self.config.set("led_enabled", new_led_enabled)
        self.config.set("led_controller_ip", led_values["ip"])
        self.config.set("led_controller_port", led_values["port"])
        self.config.set("led_width", led_values["width"])
        self.config.set("led_height", led_values["height"])
        self.config.set("led_color_mode", led_values["color_mode"])
        self.config.set("led_page_seconds", led_values["page_seconds"])
        self.config.set("led_grades_per_page", led_values["grades_per_page"])
        self.config.set("led_layout_regions", led_values["regions_per_page"])
        self.config.set("led_club_rows_per_group", led_values["club_rows_per_group"])
        self.config.set("led_club_groups_per_page", led_values["club_groups_per_page"])
        self.config.set(
            "led_dismissed_delay_seconds",
            led_values["dismissed_delay_seconds"],
        )
        self.config.set("led_show_title", led_values["show_title"])
        self.config.set("led_school_title", led_values["title"])
        # Time settings removed
        self.config.save()
        if self.sync_service and self.sync_service.api:
            self.sync_service.api.school_id = new_school_id
            self.sync_service.api.base_url = self.config.get("api_base_url", "https://rest.xxt.cn")
        
        msg = "设置已保存。"
        if self.led_service and old_led_enabled and (
            not new_led_enabled or led_target_changed or school_id_changed
        ):
            # Queue this before a school sync can enqueue its first new-school
            # refresh, especially when an older refresh is already running.
            self.led_service.clear_async(old_led_ip, old_led_port)
        if school_id_changed or api_base_url_changed:
            if self.led_service and school_id_changed:
                self.led_service.reset_statuses(school_id=old_school_id)
            self.clear_local_school_data()
            msg += "\n\n检测到学校 ID 或接口地址已变更，正在尝试应用并同步..."
            # Apply to runtime service
            if self.sync_service and self.sync_service.api:
                # Trigger sync
                self.trigger_sync(silent=True)
                msg += "\n后台同步已触发。请关注主界面日志。"
        if self.led_service:
            if new_led_enabled and not school_id_changed:
                self.led_service.refresh_async()
        
        QMessageBox.information(self, "成功", msg)
        self._closing = True
        self.accept()

    def clear_local_school_data(self):
        if self.sync_service and hasattr(self.sync_service, "db") and self.sync_service.db:
            self.sync_service.db.clear_mappings()
        self.config.set("schedules", [])
        self.config.save()

    def trigger_sync(self, silent=False):
        if self.sync_service:
            # Apply current text just in case (though save should handle it)
            # Now self.sync_service.api should work thanks to property
            if hasattr(self.sync_service, 'api') and self.sync_service.api:
                self.sync_service.api.school_id = self.school_id_edit.text().strip()

            # Call force_sync which emits signal to worker thread
            if hasattr(self.sync_service, 'force_sync'):
                self.sync_service.force_sync()
                if not silent:
                    QMessageBox.information(self, "提示", "同步指令已发送，正在后台执行。")
                else:
                    print("[Settings] Triggered sync (background)")
            else:
                 # Fallback if method missing (shouldn't happen with update)
                 if not silent:
                    QMessageBox.warning(self, "提示", "服务不支持立即同步，需等待周期执行。")
        else:
             if not silent:
                QMessageBox.warning(self, "错误", "同步服务未运行")

    def fill_local_device_no(self):
        self.device_no_edit.setText(format_device_no_from_node(uuid.getnode()))

    def _get_led_values(self, show_errors=True):
        self._led_validation_message = ""

        def fail(message):
            self._led_validation_message = message
            if show_errors:
                QMessageBox.warning(self, "错误", message)
            return None

        ip = self.led_ip_edit.text().strip()
        title = self.led_title_edit.toPlainText().strip()
        show_title = self.led_show_title_check.isChecked()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return fail("控制卡 IP 格式不正确")
        try:
            port = int(self.led_port_edit.text().strip())
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            return fail("控制卡端口必须是 1-65535 的数字")
        dimensions = validate_led_dimensions(
            self.led_width_edit.text(),
            self.led_height_edit.text(),
            self.led_color_mode_combo.currentData(),
        )
        if not dimensions.ok:
            return fail(dimensions.message)
        width, height = dimensions.width, dimensions.height
        try:
            page_seconds = float(self.led_page_seconds_edit.text().strip())
            if not 1 <= page_seconds <= 300:
                raise ValueError()
        except ValueError:
            return fail("翻页间隔必须是 1-300 秒")
        try:
            dismissed_delay_seconds = float(
                self.led_dismissed_delay_edit.text().strip()
            )
            if not 1 <= dismissed_delay_seconds <= 300:
                raise ValueError()
        except ValueError:
            return fail("已放学延迟必须是 1-300 秒")
        try:
            grades_per_page = int(self.led_grades_per_page_edit.text().strip())
            if not 1 <= grades_per_page <= 6:
                raise ValueError()
        except ValueError:
            return fail("每区行数必须是 1-6 的整数")
        try:
            regions_per_page = int(self.led_layout_regions_edit.text().strip())
            if not 1 <= regions_per_page <= 6:
                raise ValueError()
        except ValueError:
            return fail("行政班横向分区数必须是 1-6 的整数")
        try:
            club_rows_per_group = int(self.led_club_rows_edit.text().strip())
            if not 1 <= club_rows_per_group <= 6:
                raise ValueError()
        except ValueError:
            return fail("社团班每组行数必须是 1-6 的整数")
        try:
            club_groups_per_page = int(self.led_club_groups_edit.text().strip())
            if not 1 <= club_groups_per_page <= 6:
                raise ValueError()
        except ValueError:
            return fail("社团班横向组数必须是 1-6 的整数")
        if show_title and not title:
            return fail("显示左侧标题时，标题内容不能为空")
        return {
            "ip": ip,
            "port": port,
            "width": width,
            "height": height,
            "color_mode": self.led_color_mode_combo.currentData() or "single",
            "page_seconds": page_seconds,
            "grades_per_page": grades_per_page,
            "regions_per_page": regions_per_page,
            "club_rows_per_group": club_rows_per_group,
            "club_groups_per_page": club_groups_per_page,
            "dismissed_delay_seconds": dismissed_delay_seconds,
            "show_title": show_title,
            "title": title,
        }

    def _update_led_color_hint(self, *_args):
        if self.led_color_mode_combo.currentData() == "double":
            self.led_color_hint.setText(
                "双色状态：未放学=黄、放学中=红、已放学=绿；表格、标题和班级名保持红色。"
                "必须与控制卡屏参中的双色配置一致。"
            )
        else:
            self.led_color_hint.setText(
                "单色状态：未放学为空、刷卡后显示“放学中/已放学”。"
                "必须与控制卡屏参中的单色配置一致。"
            )
        self._update_led_size_hint()

    def _update_led_size_hint(self):
        if not hasattr(self, "led_size_hint"):
            return
        pixel_limit = (
            "262144（256K）"
            if self.led_color_mode_combo.currentData() == "double"
            else "524288（512K）"
        )
        self.led_size_hint.setText(
            f"填写施工方确认的实际像素：宽≤2048，高≤1024，总像素≤{pixel_limit}。"
            "只支持正整数，不强制 8/16/32 倍数；必须与控制卡配置完全一致。"
        )
    def mark_led_preview_stale(self, *_args):
        self._preview_state.mark_dirty()
        self.preview_generate_btn.setText(self._preview_state.button_label)
        if self._preview_state.has_preview:
            self.preview_status_label.setText(
                "参数已修改，当前画面仍是上一次结果；请点击“重新生成预览”。"
            )
        else:
            self.preview_status_label.setText(
                "参数已修改，请点击“生成预览”查看当前效果。"
            )

    def generate_led_preview(self):
        values = self._get_led_values(show_errors=False)
        if values is None:
            if not self._preview_state.has_preview:
                self._preview_pages = []
                self._show_preview_message("请先填写有效的 LED 配置")
                self.preview_page_label.setText("0 / 0")
            self.preview_status_label.setText(
                self._led_validation_message or "LED 配置格式不正确。"
            )
            self._update_preview_buttons()
            return
        if not self.led_service:
            self._show_preview_message("LED 服务未初始化，暂时无法生成预览")
            self.preview_status_label.setText("")
            return
        request_revision = self._preview_state.begin()
        if request_revision is None:
            return
        self.preview_generate_btn.setEnabled(False)
        self.preview_generate_btn.setText(self._preview_state.button_label)
        self.preview_status_label.setText("正在后台生成预览，请稍候…")
        request_values = dict(values)
        sample_statuses = self.preview_sample_check.isChecked()
        preview_dir = Path(get_app_root()) / "data" / "led-preview"

        def run():
            try:
                pages = self.led_service.render_preview_pages(
                    preview_dir,
                    width=request_values["width"],
                    height=request_values["height"],
                    grades_per_page=request_values["grades_per_page"],
                    regions_per_page=request_values["regions_per_page"],
                    show_title=request_values["show_title"],
                    title=request_values["title"],
                    sample_statuses=sample_statuses,
                    club_rows_per_group=request_values["club_rows_per_group"],
                    club_groups_per_page=request_values["club_groups_per_page"],
                    color_mode=request_values["color_mode"],
                )
                payload = {
                    "revision": request_revision,
                    "ok": True,
                    "pages": pages,
                    "values": request_values,
                    "error": "",
                }
            except Exception as exc:
                payload = {
                    "revision": request_revision,
                    "ok": False,
                    "pages": [],
                    "values": request_values,
                    "error": str(exc),
                }
            if not self._closing:
                self.preview_finished.emit(payload)

        threading.Thread(target=run, daemon=True).start()

    def _handle_preview_finished(self, payload):
        stale = self._preview_state.complete(
            payload["revision"],
            success=payload["ok"],
        )
        self.preview_generate_btn.setEnabled(True)
        self.preview_generate_btn.setText(self._preview_state.button_label)
        if not payload["ok"]:
            self._preview_pages = []
            self._show_preview_message("预览生成失败")
            self.preview_status_label.setText(payload["error"])
            self._update_preview_buttons()
            return
        values = payload["values"]
        self._preview_color_mode = values["color_mode"]
        self._preview_pages = payload["pages"]
        try:
            self._preview_index = min(
                self._preview_index,
                max(0, len(self._preview_pages) - 1),
            )
        except Exception:
            self._preview_index = 0
        if not self._preview_pages:
            self._show_preview_message("暂无可预览的班级")
            self.preview_status_label.setText("请先绑定学校并同步行政班或社团班数据。")
        else:
            color_summary = (
                "双色模拟：未放学黄 / 放学中红 / 已放学绿"
                if values["color_mode"] == "double"
                else "单色模拟：黑底红字，未放学为空"
            )
            self.preview_status_label.setText(
                f"{values['width']}×{values['height']} 像素 · "
                f"行政班 {values['regions_per_page']} 区×{values['grades_per_page']} 行 · "
                f"社团班 {values['club_groups_per_page']} 组×{values['club_rows_per_group']} 行 · "
                f"{color_summary}"
            )
            self._show_preview_page()
            if stale:
                self.preview_status_label.setText(
                    "预览已生成，但生成期间参数发生变化；请点击“重新生成预览”。"
                )
        self._update_preview_buttons()

    def _show_preview_page(self):
        if not self._preview_pages:
            return
        try:
            preview_image = colorize_led_preview(
                self._preview_pages[self._preview_index],
                color_mode=self._preview_color_mode,
            )
            image_bytes = BytesIO()
            preview_image.save(image_bytes, format="PNG")
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_bytes.getvalue(), "PNG"):
                raise ValueError("无法加载 LED 预览图片")
            self._preview_source_pixmap = pixmap
        except Exception as exc:
            self._show_preview_message("预览加载失败")
            self.preview_status_label.setText(str(exc))
            return
        self._apply_preview_zoom()
        self.preview_page_label.setText(
            f"{self._preview_index + 1} / {len(self._preview_pages)}"
        )

    def _show_preview_message(self, message):
        self._preview_source_pixmap = None
        self.preview_label.clear()
        self.preview_label.setText(message)
        viewport_size = self.preview_scroll.viewport().size()
        self.preview_label.resize(
            max(1, viewport_size.width()),
            max(1, viewport_size.height()),
        )

    def _apply_preview_zoom(self):
        pixmap = self._preview_source_pixmap
        if pixmap is None or pixmap.isNull():
            return
        if self._preview_fit_to_window:
            viewport = self.preview_scroll.viewport().size()
            scale = min(
                max(1, viewport.width() - 8) / pixmap.width(),
                max(1, viewport.height() - 8) / pixmap.height(),
            )
            target_width = max(1, round(pixmap.width() * scale))
            target_height = max(1, round(pixmap.height() * scale))
            self.preview_zoom_label.setText("适应")
        else:
            target_width, target_height = scaled_preview_size(
                pixmap.width(),
                pixmap.height(),
                self._preview_zoom_percent,
            )
            self.preview_zoom_label.setText(f"{self._preview_zoom_percent}%")
        scaled = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.preview_label.clear()
        self.preview_label.resize(target_width, target_height)
        self.preview_label.setPixmap(scaled)

    def zoom_preview_in(self):
        self._preview_fit_to_window = False
        self._preview_zoom_percent = min(400, self._preview_zoom_percent + 25)
        self._apply_preview_zoom()

    def zoom_preview_out(self):
        self._preview_fit_to_window = False
        self._preview_zoom_percent = max(25, self._preview_zoom_percent - 25)
        self._apply_preview_zoom()

    def reset_preview_zoom(self):
        self._preview_fit_to_window = False
        self._preview_zoom_percent = 100
        self._apply_preview_zoom()

    def fit_preview_to_window(self):
        self._preview_fit_to_window = True
        self._apply_preview_zoom()

    def _update_preview_buttons(self):
        has_multiple = len(self._preview_pages) > 1
        self.preview_prev_btn.setEnabled(has_multiple)
        self.preview_next_btn.setEnabled(has_multiple)
        if not self._preview_pages:
            self.preview_page_label.setText("0 / 0")

    def show_previous_preview_page(self):
        if self._preview_pages:
            self._preview_index = (self._preview_index - 1) % len(self._preview_pages)
            self._show_preview_page()

    def show_next_preview_page(self):
        if self._preview_pages:
            self._preview_index = (self._preview_index + 1) % len(self._preview_pages)
            self._show_preview_page()

    def _run_led_action(self, action):
        if not self.led_service:
            QMessageBox.warning(self, "LED 屏", "LED 服务未初始化")
            return
        values = self._get_led_values()
        if values is None:
            return
        self.led_connect_btn.setEnabled(False)
        self.led_screen_btn.setEnabled(False)
        self.led_restore_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self._led_action_running = True

        def run():
            try:
                result = action(values)
                if not self._closing:
                    self.led_action_finished.emit(result.ok, result.message)
            except Exception as exc:
                if not self._closing:
                    self.led_action_finished.emit(False, str(exc))

        threading.Thread(target=run, daemon=True).start()

    def test_led_connection(self):
        self._run_led_action(
            lambda values: self.led_service.test_connection(
                ip=values["ip"],
                port=values["port"],
            )
        )

    def test_led_screen(self):
        self._run_led_action(
            lambda values: self.led_service.send_test_screen(
                ip=values["ip"],
                port=values["port"],
                title=values["title"],
                stay_seconds=values["page_seconds"],
                grades_per_page=values["grades_per_page"],
                regions_per_page=values["regions_per_page"],
                show_title=values["show_title"],
                width=values["width"],
                height=values["height"],
                club_rows_per_group=values["club_rows_per_group"],
                club_groups_per_page=values["club_groups_per_page"],
                color_mode=values["color_mode"],
            )
        )

    def reset_led_screen(self):
        confirmation = QMessageBox(self)
        confirmation.setIcon(QMessageBox.Icon.Warning)
        confirmation.setWindowTitle("清空班级状态并恢复原节目？")
        confirmation.setText("将清空当前学校今天的行政班和社团班 LED 状态。")
        confirmation.setInformativeText(
            "控制卡将恢复施工方原有节目；之后再次刷卡仍可重新生成放学状态。"
        )
        confirmation.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirmation.button(QMessageBox.StandardButton.Yes).setText("清空状态并恢复")
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        self._run_led_action(
            lambda values: self.led_service.reset_and_restore(
                ip=values["ip"],
                port=values["port"],
            )
        )

    def _show_led_result(self, ok, message):
        self._led_action_running = False
        self.led_connect_btn.setEnabled(True)
        self.led_screen_btn.setEnabled(True)
        self.led_restore_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        if self._closing:
            return
        if ok:
            QMessageBox.information(self, "LED 屏", message)
        else:
            QMessageBox.warning(self, "LED 屏", message)

    def reject(self):
        self._closing = True
        super().reject()

    def closeEvent(self, event):
        self._closing = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (
            self._preview_fit_to_window
            and self._preview_source_pixmap is not None
            and not self._preview_source_pixmap.isNull()
        ):
            self._apply_preview_zoom()
