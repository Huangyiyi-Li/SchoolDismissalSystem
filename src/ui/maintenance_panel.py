from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGroupBox, QPushButton, QVBoxLayout, QWidget, QLabel


class MaintenancePanel(QWidget):
    open_settings = pyqtSignal()
    open_schedule = pyqtSignal()
    open_device_manager = pyqtSignal()
    open_mapping = pyqtSignal()
    force_sync = pyqtSignal()
    exit_maintenance = pyqtSignal()
    test_mode_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("维护模式")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        action_group = QGroupBox("管理入口")
        group_layout = QVBoxLayout(action_group)

        btn_settings = QPushButton("学校设置")
        btn_settings.clicked.connect(self.open_settings.emit)
        group_layout.addWidget(btn_settings)

        btn_schedule = QPushButton("放学时间")
        btn_schedule.clicked.connect(self.open_schedule.emit)
        group_layout.addWidget(btn_schedule)

        btn_device = QPushButton("设备管理")
        btn_device.clicked.connect(self.open_device_manager.emit)
        group_layout.addWidget(btn_device)

        btn_mapping = QPushButton("卡号映射")
        btn_mapping.clicked.connect(self.open_mapping.emit)
        group_layout.addWidget(btn_mapping)

        btn_sync = QPushButton("立即同步")
        btn_sync.clicked.connect(self.force_sync.emit)
        group_layout.addWidget(btn_sync)

        self.test_mode_check = QCheckBox("测试模式 (仅播报，不推送)")
        self.test_mode_check.stateChanged.connect(
            lambda state: self.test_mode_changed.emit(state == Qt.CheckState.Checked.value)
        )
        group_layout.addWidget(self.test_mode_check)

        btn_guard = QPushButton("返回守护模式")
        btn_guard.clicked.connect(self.exit_maintenance.emit)
        group_layout.addWidget(btn_guard)

        layout.addWidget(action_group)
        layout.addStretch(1)

    def set_test_mode(self, enabled: bool):
        self.test_mode_check.setChecked(bool(enabled))
