from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QFormLayout,
                             QCheckBox)
from PyQt6.QtCore import Qt
from ..services.device_identity import format_device_no_from_node, normalize_device_no
import uuid

class SettingsDialog(QDialog):
    def __init__(self, config_manager, data_sync_service=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.sync_service = data_sync_service
        self.setWindowTitle("绑定学校")
        self.resize(400, 150)
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

        # Buttons
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
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

        # Check if School ID changed
        old_school_id = self.config.get("school_id")
        old_api_base_url = self.config.get("api_base_url", "https://rest.xxt.cn")
        school_id_changed = new_school_id != old_school_id
        api_base_url_changed = (api_base_url or "https://rest.xxt.cn") != old_api_base_url

        self.config.set("school_id", new_school_id)
        self.config.set("api_base_url", api_base_url or "https://rest.xxt.cn")
        self.config.set("device_no", device_no)
        self.config.set("mqtt_enabled", self.mqtt_enabled_check.isChecked())
        self.config.set("udp_port", port)
        # Time settings removed
        self.config.save()
        if self.sync_service and self.sync_service.api:
            self.sync_service.api.school_id = new_school_id
            self.sync_service.api.base_url = self.config.get("api_base_url", "https://rest.xxt.cn")
        
        msg = "设置已保存。"
        if school_id_changed or api_base_url_changed:
            self.clear_local_school_data()
            msg += "\n\n检测到学校 ID 或接口地址已变更，正在尝试应用并同步..."
            # Apply to runtime service
            if self.sync_service and self.sync_service.api:
                # Trigger sync
                self.trigger_sync(silent=True)
                msg += "\n后台同步已触发。请关注主界面日志。"
        
        QMessageBox.information(self, "成功", msg)
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
