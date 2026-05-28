import json
import os
import subprocess
import sys

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..services.network_log import default_network_logger


class NetworkLogDialog(QDialog):
    def __init__(self, network_logger=None, parent=None):
        super().__init__(parent)
        self.network_logger = network_logger or default_network_logger
        self.entries = []
        self.setWindowTitle("接口日志")
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
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["时间", "协议", "方向", "接口/Topic", "结果", "耗时(ms)", "错误"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 360)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 80)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_selected_detail)
        layout.addWidget(self.table, stretch=2)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        layout.addWidget(self.detail, stretch=1)

    def load_entries(self):
        self.entries = self.network_logger.get_recent_entries(limit=500)
        self.table.setRowCount(0)
        for entry in self.entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                entry.get("timestamp", ""),
                entry.get("protocol", ""),
                entry.get("direction", ""),
                entry.get("target", ""),
                entry.get("result", ""),
                "" if entry.get("elapsed_ms") is None else str(entry.get("elapsed_ms")),
                entry.get("error", ""),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        if self.entries:
            self.table.selectRow(0)
        else:
            self.detail.setPlainText("暂无接口日志")

    def show_selected_detail(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if row < 0 or row >= len(self.entries):
            return
        self.detail.setPlainText(
            json.dumps(self.entries[row], ensure_ascii=False, indent=2)
        )

    def open_log_dir(self):
        os.makedirs(self.network_logger.log_dir, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.network_logger.log_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.network_logger.log_dir])
        else:
            subprocess.Popen(["xdg-open", self.network_logger.log_dir])
