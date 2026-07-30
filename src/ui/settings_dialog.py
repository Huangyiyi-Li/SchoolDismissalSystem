from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QFormLayout,
                             QCheckBox, QPlainTextEdit, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal
from ..services.device_identity import format_device_no_from_node, normalize_device_no
import ipaddress
import threading
import uuid

class SettingsDialog(QDialog):
    led_action_finished = pyqtSignal(bool, str)

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
        self.resize(520, 460)
        self.led_action_finished.connect(self._show_led_result)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

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

        layout.addLayout(form_layout)

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

        self.led_page_seconds_edit = QLineEdit(
            str(self.config.get("led_page_seconds", 5))
        )
        self.led_page_seconds_edit.setPlaceholderText("每页停留秒数")
        led_form.addRow("翻页间隔(秒):", self.led_page_seconds_edit)

        self.led_title_edit = QPlainTextEdit()
        self.led_title_edit.setPlainText(
            self.config.get("led_school_title", "数智家校\n放学系统")
        )
        self.led_title_edit.setMaximumHeight(72)
        self.led_title_edit.setPlaceholderText("学校名称\n数智家校\n放学系统")
        led_form.addRow("左侧标题:", self.led_title_edit)

        led_test_layout = QHBoxLayout()
        self.led_connect_btn = QPushButton("测试连接")
        self.led_connect_btn.clicked.connect(self.test_led_connection)
        led_test_layout.addWidget(self.led_connect_btn)
        self.led_screen_btn = QPushButton("发送测试画面")
        self.led_screen_btn.clicked.connect(self.test_led_screen)
        led_test_layout.addWidget(self.led_screen_btn)
        led_form.addRow("设备测试:", led_test_layout)
        layout.addWidget(led_group)

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

        layout.addLayout(btn_layout)

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
        school_id_changed = new_school_id != old_school_id
        api_base_url_changed = (api_base_url or "https://rest.xxt.cn") != old_api_base_url
        led_target_changed = (
            led_values["ip"] != old_led_ip or led_values["port"] != old_led_port
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
        self.config.set("led_page_seconds", led_values["page_seconds"])
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
                self.led_service.reset_statuses()
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

    def _get_led_values(self):
        ip = self.led_ip_edit.text().strip()
        title = self.led_title_edit.toPlainText().strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            QMessageBox.warning(self, "错误", "控制卡 IP 格式不正确")
            return None
        try:
            port = int(self.led_port_edit.text().strip())
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "错误", "控制卡端口必须是 1-65535 的数字")
            return None
        try:
            page_seconds = float(self.led_page_seconds_edit.text().strip())
            if not 1 <= page_seconds <= 300:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "错误", "翻页间隔必须是 1-300 秒")
            return None
        if not title:
            QMessageBox.warning(self, "错误", "LED 左侧标题不能为空")
            return None
        return {
            "ip": ip,
            "port": port,
            "page_seconds": page_seconds,
            "title": title,
        }

    def _run_led_action(self, action):
        if not self.led_service:
            QMessageBox.warning(self, "LED 屏", "LED 服务未初始化")
            return
        values = self._get_led_values()
        if values is None:
            return
        self.led_connect_btn.setEnabled(False)
        self.led_screen_btn.setEnabled(False)
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
            )
        )

    def _show_led_result(self, ok, message):
        self._led_action_running = False
        self.led_connect_btn.setEnabled(True)
        self.led_screen_btn.setEnabled(True)
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
