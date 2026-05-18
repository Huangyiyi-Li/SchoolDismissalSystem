from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                             QInputDialog, QLineEdit)
from PyQt6.QtCore import Qt

class DeviceManagerDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("设备管理")
        self.resize(600, 400)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["IP地址", "设备名称", "最后刷卡通信"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        
        edit_btn = QPushButton("修改名称")
        edit_btn.clicked.connect(self.edit_device_name)
        btn_layout.addWidget(edit_btn)

        refresh_btn = QPushButton("刷新列表")
        refresh_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(refresh_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def load_data(self):
        self.table.setRowCount(0)
        devices = self.db.get_devices() # [(ip, name, last_seen), ...]
        
        for row_idx, (ip, name, last_seen) in enumerate(devices):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(ip))
            self.table.setItem(row_idx, 1, QTableWidgetItem(name))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(last_seen)))

    def edit_device_name(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个设备")
            return

        ip = self.table.item(current_row, 0).text()
        current_name = self.table.item(current_row, 1).text()

        name, ok = QInputDialog.getText(self, "修改设备名称", 
                                      f"请输入IP {ip} 的新名称:", 
                                      QLineEdit.EchoMode.Normal, 
                                      current_name)
        
        if ok and name:
            if self.db.upsert_device(ip, name=name):
                self.load_data()
            else:
                QMessageBox.critical(self, "错误", "保存失败")
