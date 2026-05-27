from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QLabel, QTabWidget, QWidget, QPushButton, QHBoxLayout,
                             QGroupBox)

from ..services.class_types import format_class_type_section_title
from ..services.schedule_display import group_schedules_by_weekday_and_type

class ScheduleDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.setWindowTitle("放学时间安排")
        self.resize(600, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Title / Info
        info_label = QLabel("以下时间表由服务器同步，仅供参考。")
        info_label.setStyleSheet("color: gray; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Tab Widget for Weekdays
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        schedules = self.config.get("schedules", [])
        
        # Mapping API weekday (1-7) to Names
        weekdays = {
            1: "周一", 2: "周二", 3: "周三", 4: "周四", 
            5: "周五", 6: "周六", 7: "周日"
        }

        grouped = group_schedules_by_weekday_and_type(schedules)
        has_data = bool(grouped)

        for wd in sorted(grouped):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

            for class_type in (1, 2):
                group = QGroupBox(format_class_type_section_title(class_type))
                group_layout = QVBoxLayout(group)
                table = self.create_time_table(grouped.get(wd, {}).get(class_type, []))
                group_layout.addWidget(table)
                tab_layout.addWidget(group)

            tab_layout.addStretch(1)
            self.tabs.addTab(tab, weekdays.get(wd, f"周{wd}"))

        if not has_data:
            layout.addWidget(QLabel("暂无时间表数据，请先同步配置。"))
            self.tabs.setVisible(False)

        # Close Button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def create_time_table(self, ranges):
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["开始时间", "结束时间"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        if not ranges:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("未配置"))
            table.setItem(0, 1, QTableWidgetItem(""))
            return table

        table.setRowCount(len(ranges))
        for i, time_range in enumerate(ranges):
            start = time_range.get("startTime", "--:--")
            end = time_range.get("endTime", "--:--")
            table.setItem(i, 0, QTableWidgetItem(start))
            table.setItem(i, 1, QTableWidgetItem(end))
        return table
