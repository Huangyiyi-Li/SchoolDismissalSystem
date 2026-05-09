import os

from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt

from ..services.tts_settings import normalize_tts_rate, normalize_tts_volume
from ..utils.runtime_logging import get_runtime_log_paths


class SettingsDialog(QDialog):
    def __init__(self, config_manager, data_sync_service=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.sync_service = data_sync_service
        self.setWindowTitle("绑定学校")
        self.resize(520, 360)
        self.setup_ui()

    def _touch_parent(self):
        parent = self.parent()
        if parent and hasattr(parent, "touch_maintenance_session"):
            parent.touch_maintenance_session()

    def _require_parent_access(self, action_label: str) -> bool:
        parent = self.parent()
        if parent and hasattr(parent, "require_maintenance_access"):
            return parent.require_maintenance_access(action_label)
        return True

    def setup_ui(self):
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        
        # School ID
        self.school_id_edit = QLineEdit()
        self.school_id_edit.setText(self.config.get("school_id", ""))
        self.school_id_edit.setPlaceholderText("请输入学校ID (如 40125)")
        form_layout.addRow("学校 ID:", self.school_id_edit)
        
        # Ingress Port
        self.port_edit = QLineEdit()
        self.port_edit.setText(str(self.config.get("udp_port", 39169)))
        form_layout.addRow("接收端口:", self.port_edit)

        layout.addLayout(form_layout)

        audio_group = QGroupBox("语音播报")
        audio_layout = QFormLayout(audio_group)

        self.tts_rate_spin = QSpinBox()
        self.tts_rate_spin.setRange(80, 240)
        self.tts_rate_spin.setSingleStep(5)
        self.tts_rate_spin.setValue(normalize_tts_rate(self.config.get("tts_rate", 160)))
        self.tts_rate_spin.setSuffix(" 速率")
        audio_layout.addRow("播报语速:", self.tts_rate_spin)

        self.tts_volume_spin = QDoubleSpinBox()
        self.tts_volume_spin.setRange(20.0, 100.0)
        self.tts_volume_spin.setSingleStep(5.0)
        self.tts_volume_spin.setDecimals(0)
        self.tts_volume_spin.setValue(normalize_tts_volume(self.config.get("tts_volume", 1.0)) * 100)
        self.tts_volume_spin.setSuffix("%")
        audio_layout.addRow("播报音量:", self.tts_volume_spin)

        layout.addWidget(audio_group)

        log_paths = get_runtime_log_paths()
        log_dir = os.path.dirname(log_paths.runtime_log_path)
        hint = QLabel(
            "运行日志目录:\n"
            f"{log_dir}\n"
            f"普通日志: {os.path.basename(log_paths.runtime_log_path)}\n"
            f"崩溃日志: {os.path.basename(log_paths.crash_log_path)}\n"
            "说明: 100% 已是语音引擎最大音量，如仍偏小需要结合系统语音或外接音箱处理。"
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        layout.addWidget(hint)

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
        if not self._require_parent_access("保存学校设置"):
            self.close()
            return
        self._touch_parent()
        new_school_id = self.school_id_edit.text().strip()
        port_str = self.port_edit.text().strip()

        if not new_school_id:
            QMessageBox.warning(self, "错误", "学校 ID 不能为空")
            return

        try:
            port = int(port_str)
        except ValueError:
            QMessageBox.warning(self, "错误", "接收端口必须是数字")
            return

        # Check if School ID changed
        old_school_id = self.config.get("school_id")
        school_id_changed = new_school_id != old_school_id

        self.config.set("school_id", new_school_id)
        self.config.set("udp_port", port)
        self.config.set("tts_rate", int(self.tts_rate_spin.value()))
        self.config.set("tts_volume", float(self.tts_volume_spin.value()) / 100.0)
        self.config.save()
        
        msg = "设置已保存。"
        if school_id_changed:
            msg += "\n\n检测到学校 ID 已变更，正在尝试应用并同步..."
            # Apply to runtime service
            if self.sync_service and self.sync_service.api:
                self.sync_service.api.school_id = new_school_id
                # Trigger sync
                self.trigger_sync(silent=True)
                msg += "\n后台同步已触发。请关注主界面日志。"
        
        QMessageBox.information(self, "成功", msg)
        self.accept()

    def trigger_sync(self, silent=False):
        if not self._require_parent_access("执行立即同步"):
            self.close()
            return
        self._touch_parent()
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
