from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QLabel, 
                             QLineEdit, QMessageBox, QWidget)
from PyQt6.QtCore import Qt
from ..services.class_types import format_class_type_label

class MappingDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("卡号-班级管理")
        self.resize(600, 400)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Input Area
        input_layout = QHBoxLayout()
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("卡号 (HEX)")
        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText("班级名称")
        self.school_input = QLineEdit()
        self.school_input.setPlaceholderText("学校ID (可选)")
        
        add_btn = QPushButton("添加/更新")
        add_btn.clicked.connect(self.add_mapping)
        
        input_layout.addWidget(QLabel("卡号:"))
        input_layout.addWidget(self.card_input)
        input_layout.addWidget(QLabel("班级:"))
        input_layout.addWidget(self.class_input)
        input_layout.addWidget(QLabel("学校ID:"))
        input_layout.addWidget(self.school_input)
        input_layout.addWidget(add_btn)
        
        layout.addLayout(input_layout)

        # Table Area
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["卡号", "类型", "classId", "名称", "学校ID", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        layout.addWidget(self.table)

    def load_data(self):
        rows = self.db.get_all_mappings()
        self.table.setRowCount(0)
        for row in rows:
            # row: card_id, class_type, class_id, class_name, school_id
            self.add_row_to_table(row[0], row[1], row[2], row[3], row[4])

    def add_row_to_table(self, card_id, class_type, class_id, class_name, school_id):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        
        self.table.setItem(row_idx, 0, QTableWidgetItem(card_id))
        self.table.setItem(row_idx, 1, QTableWidgetItem(format_class_type_label(class_type)))
        self.table.setItem(row_idx, 2, QTableWidgetItem(str(class_id) if class_id else ""))
        self.table.setItem(row_idx, 3, QTableWidgetItem(class_name))
        self.table.setItem(row_idx, 4, QTableWidgetItem(str(school_id) if school_id else ""))
        
        del_btn = QPushButton("删除")
        del_btn.setStyleSheet("color: red;")
        del_btn.clicked.connect(lambda: self.delete_mapping(card_id))
        self.table.setCellWidget(row_idx, 5, del_btn)

    def add_mapping(self):
        card_id = self.card_input.text().strip().upper()
        class_name = self.class_input.text().strip()
        school_id = self.school_input.text().strip()
        
        if not card_id or not class_name:
            QMessageBox.warning(self, "错误", "卡号和班级不能为空")
            return

        if self.db.add_mapping(card_id, class_name, school_id=school_id):
            self.load_data()
            self.card_input.clear()
            self.class_input.clear()
            self.school_input.clear()
            QMessageBox.information(self, "成功", "添加成功")
        else:
            QMessageBox.critical(self, "错误", "数据库错误")

    def delete_mapping(self, card_id):
        confirm = QMessageBox.question(self, "确认", f"确定要删除卡号 {card_id} 吗？", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_mapping(card_id)
            self.load_data()
