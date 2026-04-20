from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGroupBox, QTableWidget, QTableWidgetItem, QListWidget, 
                             QLabel, QHeaderView, QToolBar)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtCore import Qt, QTimer
# Fix import paths assuming running from project root or having src in pythonpath
# For robustness in simple script execution, we might need sys.path hacks in main
from .mapping_dialog import MappingDialog

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
        
        device_action = QAction("设备管理", self)
        device_action.triggered.connect(self.open_device_manager)
        toolbar.addAction(device_action)
        
        # Central Widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # Left Panel (Status + Devices)
        left_layout = QVBoxLayout()
        
        # Connection Status Group
        dev_group = QGroupBox("设备状态")
        dev_layout = QVBoxLayout()
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(4)
        self.device_table.setHorizontalHeaderLabels(["IP地址", "设备名称", "最后通信", "状态"])
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        dev_layout.addWidget(self.device_table)
        dev_group.setLayout(dev_layout)
        left_layout.addWidget(dev_group)
        
        # Time Window Status
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        window_str = f"{self.config.get('time_window_start')} - {self.config.get('time_window_end')}"
        self.window_label = QLabel(f"播报时段: {window_str}")
        self.window_label.setStyleSheet("font-size: 14px; font-weight: bold;")
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
        self.log_table.setHorizontalHeaderLabels(["时间", "卡号", "班级", "动作", "详细原因"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Allow resize
        self.log_table.setColumnWidth(0, 100) # Time
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
        self.udp_server.device_updated.connect(self.update_device_status)
        
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

    def open_device_manager(self):
        from .device_manager_dialog import DeviceManagerDialog
        dialog = DeviceManagerDialog(self.db, self)
        dialog.exec()
        # Refresh main UID device table names if needed?
        # The udp_server will update on next heartbeat, forcing full refresh is complex 
        # unless we reload table from DB.
        # For MVP, wait for next heartbeat or manually clear table.
        self.device_table.setRowCount(0) 

    def update_device_status(self, ip, time_str, status, name=None):
        # Allow name to be optional for backward compatibility signals, though we updated signal
        if name is None:
            name = ip 

        # Find if row exists for IP
        found = False
        for row in range(self.device_table.rowCount()):
            if self.device_table.item(row, 0).text() == ip:
                self.device_table.setItem(row, 1, QTableWidgetItem(name)) # Col 1 used to be time?
                # Wait, layout was: "IP地址", "最后通信", "状态"
                # Let's change layout to 4 columns or replace IP with Name?
                # User asked to "modify IP" (change display to Name).
                # Let's show: Name(IP) | Time | Status
                
                # Update cols: 0=IP/Name, 1=Time, 2=Status?
                # Or add column? 
                pass 
                
        # Better: Re-init columns in setup_ui to: IP | 名称 | 时间 | 状态
        # But setup_ui is already run.
        # Let's change standard behavior: 
        # Col 0: IP
        # Col 1: Name (New!)
        # Col 2: Time
        # Col 3: Status
        
        # NOTE: If we change columns dynamically here it might break.
        # Ideally we refactor setup_ui or just update existing rows.
        # If we stick to 3 cols: IP | Time | Status
        # We can put Name in Col 0: "Name (IP)"
        
        display_name = f"{name} ({ip})" if name != ip else ip
        
        for row in range(self.device_table.rowCount()):
            # Store IP in data or verify against parsing
            # Or just use row matching if we store IP in a hidden way?
            # Simple match against display string contains IP?
            # Or keep column 0 as pure IP and add Name column?
            # Let's try adding column if column count is 3.
            pass

        # To avoid complex refactor mid-flight:
        # Just update the existing logic to find row by iterate
        
        # Redo for safety:
        # Col 0: IP (Hidden?) or Visible
        # Col 1: Name 
        # Col 2: Time
        # Col 3: Status
        
        # Current: IP, Time, Status.
        # I will change setup_ui to 4 columns.
        pass
        
        # Actually, let's just do it cleanly.
        found = False
        for row in range(self.device_table.rowCount()):
            if self.device_table.item(row, 0).text() == ip:
                self.device_table.setItem(row, 1, QTableWidgetItem(name))
                self.device_table.setItem(row, 2, QTableWidgetItem(time_str))
                status_item = QTableWidgetItem(status)
                status_item.setForeground(QColor("green" if status == "在线" else "red"))
                self.device_table.setItem(row, 3, status_item)
                found = True
                break
        
        if not found:
            row = self.device_table.rowCount()
            self.device_table.insertRow(row)
            self.device_table.setItem(row, 0, QTableWidgetItem(ip))
            self.device_table.setItem(row, 1, QTableWidgetItem(name))
            self.device_table.setItem(row, 2, QTableWidgetItem(time_str))
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor("green" if status == "在线" else "red"))
            self.device_table.setItem(row, 3, status_item)

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

    def add_log(self, time_str, card_id, class_name, action, reason=""):
        self.log_table.insertRow(0)
        self.log_table.setItem(0, 0, QTableWidgetItem(time_str))
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
        if self.log_table.rowCount() > 100:
            self.log_table.removeRow(100)

    def load_recent_logs(self):
        logs = self.db.get_recent_logs()
        for log in logs:
            # log format: (swipe_time, card_id, class_name, full_status)
            # full_status might be "Action (Reason)" or just "Action"
            try:
                dt = log[0].split(' ')[1]
            except:
                dt = log[0]
            
            full_status = log[3]
            action = full_status
            reason = ""
            
            # Simple parse for backward compatibility display
            if "(" in full_status and full_status.endswith(")"):
                parts = full_status.split(" (", 1)
                action = parts[0]
                reason = parts[1][:-1] # remove trailing )
                
            self.add_log(dt, log[1], log[2], action, reason)

    def update_status_bar(self):
        # Update Time Window Display
        schedules = self.config.get("schedules")
        window_text = "默认: " + f"{self.config.get('time_window_start')} - {self.config.get('time_window_end')}"
        
        if schedules:
            import datetime
            current_weekday = datetime.datetime.now().weekday() + 1
            today_rules = [s for s in schedules if s.get("weekday") == current_weekday]
            if today_rules:
                ranges_str_list = []
                for rule in today_rules:
                    for r in rule.get("timeRanges", []):
                        start = r.get("startTime")
                        end = r.get("endTime")
                        # Filter out empty/zero times if any
                        if start != "00:00" or end != "00:00":
                             ranges_str_list.append(f"{start}-{end}")
                
                if ranges_str_list:
                    window_text = "今日: " + ", ".join(ranges_str_list)

        self.window_label.setText(f"播报时段: {window_text}")

        # Update Status
        if self.broadcast_manager.is_within_time_window():
             self.status_label.setText("当前状态: [监测中] 播报时段内")
             self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
             self.status_label.setText("当前状态: [待机] 非播报时段")
             self.status_label.setStyleSheet("color: gray;")
