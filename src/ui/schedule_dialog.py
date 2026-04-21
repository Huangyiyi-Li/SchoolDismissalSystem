from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QLabel, QTabWidget, QWidget, QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt
import datetime

class ScheduleDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.setWindowTitle("放学时间安排")
        self.resize(600, 400)
        self.setup_ui()

    def _touch_parent(self):
        parent = self.parent()
        if parent and hasattr(parent, "touch_maintenance_session"):
            parent.touch_maintenance_session()

    def setup_ui(self):
        self._touch_parent()
        layout = QVBoxLayout(self)

        # Title / Info
        info_label = QLabel("以下时间表由服务器同步，仅供参考。")
        info_label.setProperty("muted", True)
        info_label.setStyleSheet("font-style: italic; margin-bottom: 10px;")
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

        # Create tabs for Monday - Sunday (or just Mon-Fri based on data)
        # We'll create 1-5 (or 1-7) fixed tabs or dynamic? 
        # Requirement said "Monday to Thursday", but let's show all available.
        
        has_data = False
        sorted_schedules = sorted(schedules, key=lambda x: x.get("weekday", 0))

        for item in sorted_schedules:
            wd = item.get("weekday")
            name = weekdays.get(wd, f"周{wd}")
            
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            
            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["开始时间", "结束时间"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            
            ranges = item.get("timeRanges", [])
            table.setRowCount(len(ranges))
            
            for i, r in enumerate(ranges):
                start = r.get("startTime", "--:--")
                end = r.get("endTime", "--:--")
                table.setItem(i, 0, QTableWidgetItem(start))
                table.setItem(i, 1, QTableWidgetItem(end))
            
            tab_layout.addWidget(table)
            self.tabs.addTab(tab, name)
            has_data = True

        if not has_data:
            layout.addWidget(QLabel("暂无时间表数据，请先同步配置。"))
            self.tabs.setVisible(False)

        # Close Button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
