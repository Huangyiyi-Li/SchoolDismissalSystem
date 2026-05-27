from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGroupBox, QTableWidget, QTableWidgetItem,
                             QLabel, QHeaderView, QMessageBox, QToolBar)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtCore import Qt, QTimer
# Fix import paths assuming running from project root or having src in pythonpath
# For robustness in simple script execution, we might need sys.path hacks in main
from .mapping_dialog import MappingDialog
from ..services.log_records import format_log_timestamp
from ..services.dismissal_window import format_window_label

class MainWindow(QMainWindow):
    def __init__(self, config_manager, db_manager, broadcast_manager, udp_server, data_sync_service=None):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.broadcast_manager = broadcast_manager
        self.udp_server = udp_server
        self.data_sync_service = data_sync_service
        
        self.setWindowTitle("校园放学语音播报系统")
        self.resize(1024, 768)
        
        self.setup_ui()
        self.connect_signals()
        
        # Initial logs load
        self.load_recent_logs()
        
        # Start timer to refresh time display
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status_bar)
        self.timer.start(1000)

        # Apply Modern Stylesheet
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5;
            }
            QGroupBox {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTableWidget {
                border: none;
                gridline-color: #f0f0f0;
                selection-background-color: #e6f7ff;
                selection-color: black;
            }
            QHeaderView::section {
                background-color: #fafafa;
                padding: 4px;
                border: none;
                font-weight: bold;
            }
            QListWidget {
                border: none;
                font-size: 14px;
            }
            QLabel {
                color: #333;
            }
            QToolBar {
                background-color: white;
                border-bottom: 1px solid #e0e0e0;
                spacing: 10px;
            }
            QToolButton {
                padding: 5px;
                border-radius: 4px;
            }
            QToolButton:hover {
                background-color: #f0f0f0;
            }
        """)

    def setup_ui(self):
        # Menu / Toolbar
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        
        manage_action = QAction("卡号管理", self)
        manage_action.triggered.connect(self.open_mapping_dialog)
        toolbar.addAction(manage_action)

        config_action = QAction("绑定学校", self)
        config_action.triggered.connect(self.open_settings_dialog)
        toolbar.addAction(config_action)
        
        schedule_action = QAction("放学时间", self)
        schedule_action.triggered.connect(self.open_schedule_dialog)
        toolbar.addAction(schedule_action)

        startup_action = QAction("开机自启", self)
        startup_action.triggered.connect(self.enable_startup)
        toolbar.addAction(startup_action)
        
        # Central Widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # Left Panel (Status)
        left_layout = QVBoxLayout()

        # Time Window Status
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        window_str = f"{self.config.get('time_window_start')} - {self.config.get('time_window_end')}"
        self.window_label = QLabel(f"播报时段:\n{window_str}")
        self.window_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.window_label.setWordWrap(True)
        self.status_label = QLabel("当前状态: 初始化...")
        
        # Test Mode Checkbox
        from PyQt6.QtWidgets import QCheckBox
        self.test_mode_check = QCheckBox("测试模式 (仅播报，不推送)")
        self.test_mode_check.setChecked(self.config.get("test_mode", False))
        self.test_mode_check.stateChanged.connect(self.toggle_test_mode)
        
        status_layout.addWidget(self.window_label)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.test_mode_check)
        status_group.setLayout(status_layout)
        left_layout.addWidget(status_group)
        
        main_layout.addLayout(left_layout, stretch=1)

        # Center Panel (Logs) - NOW TAKES FULL WIDTH
        center_layout = QVBoxLayout()
        log_group = QGroupBox("实时日志")
        log_layout = QVBoxLayout()
        self.log_table = QTableWidget()
        
        # Updated Columns: Time, Card, Class, Action, Reason
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["刷卡时间", "卡号", "班级", "动作", "详细原因"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Allow resize
        self.log_table.setColumnWidth(0, 170) # Time
        self.log_table.setColumnWidth(1, 100) # Card
        self.log_table.setColumnWidth(2, 100) # Class
        self.log_table.setColumnWidth(3, 120) # Action
        self.log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Reason fills rest
        
        log_layout.addWidget(self.log_table)
        log_group.setLayout(log_layout)
        # Add to main with stretch
        main_layout.addWidget(log_group, stretch=3)

        # Right Panel (Queue) REMOVED as per request

    def connect_signals(self):
        # UDP Signals
        self.udp_server.card_swiped.connect(self.broadcast_manager.process_swipe)
        
        # Broadcast Signals
        self.broadcast_manager.log_updated.connect(self.add_log)
        # Assuming we might want to visualize queue later, 
        # but currently BroadcastManager's worker consumes queue immediately.
        # We can add a signal in TTSWorker when item starts/ends if strict visualization needed.

    def open_mapping_dialog(self):
        dialog = MappingDialog(self.db, self)
        dialog.exec()

    def open_settings_dialog(self):
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self.data_sync_service, self)
        dialog.exec()

    def open_schedule_dialog(self):
        from .schedule_dialog import ScheduleDialog
        dialog = ScheduleDialog(self.config, self)
        dialog.exec()

    def enable_startup(self):
        from ..services.startup_task import enable_startup_task
        result = enable_startup_task()
        if result.success:
            QMessageBox.information(self, result.title, result.message)
        else:
            QMessageBox.warning(self, result.title, result.message)

    def toggle_test_mode(self, state):
        is_test = (state == Qt.CheckState.Checked.value) or (state == 2) # Qt.CheckState or int
        self.config.set("test_mode", is_test)
        # ConfigManager set doesn't auto-save always? We should save or keep runtime.
        # BroadcastManager reads from config each time in new logic?
        # Actually logic reads: self.config.get("test_mode") in process_swipe.
        # So updating config dict is enough. But better save to persist.
        # self.config.save() # Optional, user choice if test mode persists.
        status_text = "已开启 (API推送禁用)" if is_test else "已关闭 (正常模式)"
        print(f"[Main] Test Mode {status_text}")
        
        # Visual feedback?
        if is_test:
            self.test_mode_check.setStyleSheet("color: blue; font-weight: bold;")
        else:
            self.test_mode_check.setStyleSheet("")

    def add_log(self, timestamp, card_id, class_name, action, reason=""):
        self.log_table.insertRow(0)
        self.log_table.setItem(0, 0, QTableWidgetItem(format_log_timestamp(timestamp)))
        self.log_table.setItem(0, 1, QTableWidgetItem(card_id))
        self.log_table.setItem(0, 2, QTableWidgetItem(class_name))
        
        action_item = QTableWidgetItem(action)
        if "播报" in action:
            action_item.setForeground(QColor("green"))
        elif "跳过" in action:
            action_item.setForeground(QColor("orange"))
            
        self.log_table.setItem(0, 3, action_item)
        self.log_table.setItem(0, 4, QTableWidgetItem(reason))
        
        # Limit rows
        if self.log_table.rowCount() > 500:
            self.log_table.removeRow(500)

    def load_recent_logs(self):
        logs = self.db.get_recent_logs(limit=500)
        for log in reversed(logs):
            # log format: (swipe_time, card_id, class_name, full_status)
            # full_status might be "Action (Reason)" or just "Action"
            timestamp = format_log_timestamp(log[0])
            
            full_status = log[3]
            action = full_status
            reason = ""
            
            # Simple parse for backward compatibility display
            if "(" in full_status and full_status.endswith(")"):
                parts = full_status.split(" (", 1)
                action = parts[0]
                reason = parts[1][:-1] # remove trailing )
                
            self.add_log(timestamp, log[1], log[2], action, reason)

    def update_status_bar(self):
        # Update Time Window Display
        schedules = self.config.get("schedules")
        window_text = format_window_label(
            schedules,
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
        )

        self.window_label.setText(f"播报时段:\n{window_text}")

        # Update Status
        if self.config.get("test_mode", False):
             self.status_label.setText("当前状态: [测试模式] 任意时间仅播报，不推送")
             self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        elif self.broadcast_manager.is_within_time_window():
             self.status_label.setText("当前状态: [监测中] 播报时段内")
             self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
             self.status_label.setText("当前状态: [待机] 非播报时段")
             self.status_label.setStyleSheet("color: gray;")
