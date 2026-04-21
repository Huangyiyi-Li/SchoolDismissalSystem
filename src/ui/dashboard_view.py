from __future__ import annotations

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)


class DashboardView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.banner_label = QLabel("系统状态: 初始化中")
        self.banner_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(self.banner_label)

        cards_row = QHBoxLayout()
        layout.addLayout(cards_row)

        runtime_group = QGroupBox("运行状态")
        runtime_layout = QVBoxLayout(runtime_group)
        self.runtime_label = QLabel("运行状态: --")
        runtime_layout.addWidget(self.runtime_label)
        cards_row.addWidget(runtime_group)

        devices_group = QGroupBox("在线设备")
        devices_layout = QVBoxLayout(devices_group)
        self.devices_label = QLabel("在线设备: 0 台")
        devices_layout.addWidget(self.devices_label)
        cards_row.addWidget(devices_group)

        window_group = QGroupBox("播报时段")
        window_layout = QVBoxLayout(window_group)
        self.window_label = QLabel("默认: 16:30 - 18:30")
        window_layout.addWidget(self.window_label)
        cards_row.addWidget(window_group)

        logs_group = QGroupBox("实时日志")
        logs_layout = QVBoxLayout(logs_group)
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["时间", "卡号", "班级", "动作", "详细原因"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.log_table.setColumnWidth(0, 100)
        self.log_table.setColumnWidth(1, 100)
        self.log_table.setColumnWidth(2, 100)
        self.log_table.setColumnWidth(3, 120)
        self.log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        logs_layout.addWidget(self.log_table)
        layout.addWidget(logs_group)

    def set_banner(self, text: str, should_pulse: bool):
        if should_pulse:
            style = "font-size: 16px; font-weight: bold; color: #b00020; padding: 8px;"
        else:
            style = "font-size: 16px; font-weight: bold; color: #222; padding: 8px;"
        self.banner_label.setStyleSheet(style)
        self.banner_label.setText(text)

    def set_runtime_text(self, text: str):
        self.runtime_label.setText(text)

    def set_devices_text(self, text: str):
        self.devices_label.setText(text)

    def set_window_text(self, text: str):
        self.window_label.setText(text)

    def add_log_row(self, time_str: str, card_id: str, class_name: str, action: str, reason: str):
        self.log_table.insertRow(0)
        self.log_table.setItem(0, 0, QTableWidgetItem(time_str))
        self.log_table.setItem(0, 1, QTableWidgetItem(card_id))
        self.log_table.setItem(0, 2, QTableWidgetItem(class_name))
        self.log_table.setItem(0, 3, QTableWidgetItem(action))
        self.log_table.setItem(0, 4, QTableWidgetItem(reason))
        if self.log_table.rowCount() > 100:
            self.log_table.removeRow(100)

