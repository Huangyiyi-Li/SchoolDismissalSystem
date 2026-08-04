import json
import os
import subprocess
import sys

from PyQt6.QtCore import QTimer

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..services.operation_log import default_operation_logger


class OperationLogDialog(QDialog):
    def __init__(self, operation_logger=None, parent=None):
        super().__init__(parent)
        self.operation_logger = operation_logger or default_operation_logger
        self.entries = []
        self.filtered_entries = []
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(250)
        self.filter_timer.timeout.connect(self.apply_filters)
        self.setWindowTitle("本地日志")
        self.resize(980, 620)
        self.setup_ui()
        self.load_entries()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_entries)
        button_layout.addWidget(refresh_btn)
        open_dir_btn = QPushButton("打开日志目录")
        open_dir_btn.clicked.connect(self.open_log_dir)
        button_layout.addWidget(open_dir_btn)
        self.summary_label = QLabel("")
        button_layout.addWidget(self.summary_label)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        filter_layout = QHBoxLayout()
        self.result_filter = QComboBox()
        self.result_filter.addItems(["全部结果", "success", "fail", "info"])
        self.result_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(QLabel("结果"))
        filter_layout.addWidget(self.result_filter)
        self.keyword_filter = QLineEdit()
        self.keyword_filter.setPlaceholderText("按来源、操作、班级、LED 地址或错误搜索")
        self.keyword_filter.textChanged.connect(self.schedule_filter)
        filter_layout.addWidget(QLabel("关键词"))
        filter_layout.addWidget(self.keyword_filter, stretch=1)
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["时间", "来源", "分类", "操作", "对象", "结果", "说明"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 170)
        self.table.setColumnWidth(5, 75)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_selected_detail)
        layout.addWidget(self.table, stretch=2)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        layout.addWidget(self.detail, stretch=1)

    def load_entries(self):
        self.entries = self.operation_logger.get_recent_entries(limit=500)
        self.apply_filters()

    def schedule_filter(self, *_args):
        self.filter_timer.start()

    def apply_filters(self):
        result = self.result_filter.currentText()
        keyword = self.keyword_filter.text().strip().lower()
        self.filtered_entries = []
        for entry in self.entries:
            if result != "全部结果" and entry.get("result", "") != result:
                continue
            if keyword and keyword not in json.dumps(entry, ensure_ascii=False).lower():
                continue
            self.filtered_entries.append(entry)

        self.table.setRowCount(0)
        for entry in self.filtered_entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                entry.get("timestamp", ""),
                entry.get("source", ""),
                entry.get("category", ""),
                entry.get("action", ""),
                entry.get("target", ""),
                entry.get("result", ""),
                entry.get("detail", ""),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.summary_label.setText(
            f"当前 {len(self.filtered_entries)} 条 / 最近 {len(self.entries)} 条"
        )
        if self.filtered_entries:
            self.table.selectRow(0)
        else:
            self.detail.setPlainText("暂无匹配的本地日志")

    def show_selected_detail(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if 0 <= row < len(self.filtered_entries):
            self.detail.setPlainText(
                json.dumps(self.filtered_entries[row], ensure_ascii=False, indent=2)
            )

    def open_log_dir(self):
        os.makedirs(self.operation_logger.log_dir, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.operation_logger.log_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.operation_logger.log_dir])
        else:
            subprocess.Popen(["xdg-open", self.operation_logger.log_dir])
