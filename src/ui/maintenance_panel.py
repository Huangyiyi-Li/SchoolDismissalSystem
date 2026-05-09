from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)

        intro_card = QFrame()
        intro_card.setObjectName("introCard")
        intro_layout = QVBoxLayout(intro_card)
        intro_layout.setContentsMargins(22, 20, 22, 20)
        intro_layout.setSpacing(6)

        eyebrow = QLabel("MAINTENANCE ACCESS")
        eyebrow.setObjectName("eyebrow")
        intro_layout.addWidget(eyebrow)

        title = QLabel("维护模式")
        title.setObjectName("title")
        intro_layout.addWidget(title)

        desc = QLabel("仅管理员可见。这里保留配置、同步、设备和调试操作，超时后会自动回到值守看板。")
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        intro_layout.addWidget(desc)

        layout.addWidget(intro_card)

        action_group = QGroupBox("管理入口")
        action_group.setObjectName("actionGroup")
        group_layout = QVBoxLayout(action_group)
        group_layout.setContentsMargins(20, 20, 20, 20)
        group_layout.setSpacing(12)

        btn_settings = self._create_action_button("学校设置", "维护学校编号、端口和基础配置")
        btn_settings.clicked.connect(self.open_settings.emit)
        group_layout.addWidget(btn_settings)

        btn_schedule = self._create_action_button("放学时间", "查看同步后的时间窗口和课表状态")
        btn_schedule.clicked.connect(self.open_schedule.emit)
        group_layout.addWidget(btn_schedule)

        btn_device = self._create_action_button("设备管理", "查看设备名称、在线情况和管理状态")
        btn_device.clicked.connect(self.open_device_manager.emit)
        group_layout.addWidget(btn_device)

        btn_mapping = self._create_action_button("卡号映射", "维护班级与卡号关系")
        btn_mapping.clicked.connect(self.open_mapping.emit)
        group_layout.addWidget(btn_mapping)

        btn_sync = self._create_action_button("立即同步", "立刻刷新班级、时间表和远端配置")
        btn_sync.clicked.connect(self.force_sync.emit)
        group_layout.addWidget(btn_sync)

        self.test_mode_check = QCheckBox("测试模式（仅播报，不推送）")
        self.test_mode_check.setObjectName("testModeCheck")
        self.test_mode_check.stateChanged.connect(
            lambda state: self.test_mode_changed.emit(state == Qt.CheckState.Checked.value)
        )
        group_layout.addWidget(self.test_mode_check)

        btn_guard = QPushButton("返回值守看板")
        btn_guard.setObjectName("secondaryButton")
        btn_guard.clicked.connect(self.exit_maintenance.emit)
        group_layout.addWidget(btn_guard)

        layout.addWidget(action_group)
        layout.addStretch(1)

    def _create_action_button(self, title: str, desc: str) -> QPushButton:
        button = QPushButton(f"{title}\n{desc}")
        button.setObjectName("actionButton")
        return button

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #08111f;
                color: #d8e4f4;
                font-family: "Segoe UI", "PingFang SC", sans-serif;
            }
            QFrame#introCard, QGroupBox#actionGroup {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1829, stop:1 #101f34);
                border: 1px solid #1d3552;
                border-radius: 18px;
            }
            QGroupBox#actionGroup {
                margin-top: 14px;
                padding-top: 12px;
                font-size: 13px;
                font-weight: 700;
                color: #8ecdf1;
            }
            QGroupBox#actionGroup::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px;
            }
            QLabel#eyebrow {
                color: #7dd3fc;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#title {
                color: #f8fbff;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#desc {
                color: #8ea3bd;
                font-size: 13px;
            }
            QPushButton#actionButton, QPushButton#secondaryButton {
                background: #0f2035;
                border: 1px solid #244362;
                border-radius: 14px;
                color: #eaf2ff;
                font-size: 14px;
                font-weight: 600;
                padding: 14px 16px;
                text-align: left;
            }
            QPushButton#actionButton:hover, QPushButton#secondaryButton:hover {
                background: #15314f;
                border-color: #37638f;
            }
            QPushButton#secondaryButton {
                background: #141b27;
                border-color: #313f51;
            }
            QCheckBox#testModeCheck {
                color: #f8fbff;
                font-size: 14px;
                font-weight: 600;
                padding: 8px 4px;
            }
            QCheckBox#testModeCheck::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox#testModeCheck::indicator:unchecked {
                border: 1px solid #406182;
                background: #0d1829;
                border-radius: 4px;
            }
            QCheckBox#testModeCheck::indicator:checked {
                border: 1px solid #60a5fa;
                background: #1d4ed8;
                border-radius: 4px;
            }
            """
        )

    def set_test_mode(self, enabled: bool):
        self.test_mode_check.setChecked(bool(enabled))
