from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGroupBox, QTableWidget, QTableWidgetItem,
                             QLabel, QHeaderView, QMessageBox, QToolBar)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtCore import Qt, QTimer
# Fix import paths assuming running from project root or having src in pythonpath
# For robustness in simple script execution, we might need sys.path hacks in main
from ..app_info import APP_NAME, APP_VERSION_LABEL
from .mapping_dialog import MappingDialog
from ..services.log_records import format_log_timestamp
from ..services.class_types import format_class_type_label
from ..services.dismissal_window import format_grouped_window_label


def format_schedule_status_html(window_text):
    lines = window_text.splitlines()
    html_lines = []
    for line in lines:
        if not line:
            html_lines.append("<br>")
        elif "年" in line and "星期" in line:
            html_lines.append(
                f"<div style='color:#1f2937;font-size:15px;font-weight:600;'>{line}</div>"
            )
        elif line == "行政班放学时段":
            html_lines.append(
                f"<div style='color:#0f766e;font-weight:700;margin-top:8px;'>{line}</div>"
            )
        elif line == "社团班放学时段":
            html_lines.append(
                f"<div style='color:#7c3aed;font-weight:700;margin-top:8px;'>{line}</div>"
            )
        elif line == "未配置":
            html_lines.append(f"<div style='color:#9ca3af;font-weight:400;'>{line}</div>")
        else:
            html_lines.append(f"<div style='color:#374151;font-weight:500;'>{line}</div>")
    return "".join(html_lines)

class MainWindow(QMainWindow):
    def __init__(
        self,
        config_manager,
        db_manager,
        broadcast_manager,
        udp_server,
        data_sync_service=None,
        led_service=None,
    ):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.broadcast_manager = broadcast_manager
        self.udp_server = udp_server
        self.data_sync_service = data_sync_service
        self.led_service = led_service
        self._test_mode_reset_on_startup = bool(self.config.get("test_mode", False))
        if self._test_mode_reset_on_startup:
            self.config.set("test_mode", False)
        
        self.setWindowTitle(APP_NAME)
        self.resize(1024, 768)
        
        self.setup_ui()
        if self._test_mode_reset_on_startup:
            self._log_test_mode_change(False, "启动时自动关闭上次残留的测试模式")
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

        network_log_action = QAction("接口日志", self)
        network_log_action.triggered.connect(self.open_network_log_dialog)
        toolbar.addAction(network_log_action)

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
        initial_window_text = format_grouped_window_label(
            self.config.get("schedules"),
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
        )
        self.window_label = QLabel(format_schedule_status_html(initial_window_text))
        self.window_label.setTextFormat(Qt.TextFormat.RichText)
        self.window_label.setStyleSheet("font-size: 14px;")
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
        version_label = QLabel(APP_VERSION_LABEL)
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        version_label.setStyleSheet("color: #6b7280; font-size: 12px; font-weight: 400;")
        status_layout.addWidget(version_label)
        status_group.setLayout(status_layout)
        left_layout.addWidget(status_group)
        
        main_layout.addLayout(left_layout, stretch=1)

        # Center Panel (Logs) - NOW TAKES FULL WIDTH
        center_layout = QVBoxLayout()
        log_group = QGroupBox("实时日志")
        log_layout = QVBoxLayout()
        self.log_table = QTableWidget()
        
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels(["时间", "来源", "类型", "名称", "动作", "详细原因"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Allow resize
        self.log_table.setColumnWidth(0, 170) # Time
        self.log_table.setColumnWidth(1, 140) # Source
        self.log_table.setColumnWidth(2, 90) # Type
        self.log_table.setColumnWidth(3, 140) # Name
        self.log_table.setColumnWidth(4, 120) # Action
        self.log_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch) # Reason fills rest
        
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
        dialog = SettingsDialog(
            self.config,
            self.data_sync_service,
            led_service=self.led_service,
            parent=self,
        )
        dialog.exec()

    def open_schedule_dialog(self):
        from .schedule_dialog import ScheduleDialog
        dialog = ScheduleDialog(self.config, self)
        dialog.exec()

    def open_network_log_dialog(self):
        from .network_log_dialog import NetworkLogDialog
        dialog = NetworkLogDialog(parent=self)
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
        old_value = bool(self.config.get("test_mode", False))
        if is_test and not old_value:
            reply = QMessageBox.question(
                self,
                "确认开启测试模式",
                "开启测试模式后，刷卡只会本地播报，不会推送到服务端后台。确认开启吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.test_mode_check.blockSignals(True)
                self.test_mode_check.setChecked(False)
                self.test_mode_check.blockSignals(False)
                return
        self.config.set("test_mode", is_test)
        # ConfigManager set doesn't auto-save always? We should save or keep runtime.
        # BroadcastManager reads from config each time in new logic?
        # Actually logic reads: self.config.get("test_mode") in process_swipe.
        # So updating config dict is enough. But better save to persist.
        # self.config.save() # Optional, user choice if test mode persists.
        status_text = "已开启 (API推送禁用)" if is_test else "已关闭 (正常模式)"
        print(f"[Main] Test Mode {status_text}")
        if old_value != is_test:
            self._log_test_mode_change(
                is_test,
                "用户在主界面切换；开启后仅本地播报，不推送服务端",
            )
        
        # Visual feedback?
        if is_test:
            self.test_mode_check.setStyleSheet("color: blue; font-weight: bold;")
        else:
            self.test_mode_check.setStyleSheet("")

    def _log_test_mode_change(self, enabled, reason):
        action = "开启" if enabled else "关闭"
        self.broadcast_manager._log_event(
            "",
            "测试模式",
            action,
            reason,
            source="系统设置",
            source_detail="test_mode",
        )

    def add_log(self, timestamp, source, target_type, target_name, action, reason=""):
        self.log_table.insertRow(0)
        self.log_table.setItem(0, 0, QTableWidgetItem(format_log_timestamp(timestamp)))
        self.log_table.setItem(0, 1, QTableWidgetItem(source))
        self.log_table.setItem(0, 2, QTableWidgetItem(target_type))
        self.log_table.setItem(0, 3, QTableWidgetItem(target_name))
        
        action_item = QTableWidgetItem(action)
        if "播报" in action:
            action_item.setForeground(QColor("green"))
        elif "跳过" in action:
            action_item.setForeground(QColor("orange"))
            
        self.log_table.setItem(0, 4, action_item)
        self.log_table.setItem(0, 5, QTableWidgetItem(reason))
        
        # Limit rows
        if self.log_table.rowCount() > 500:
            self.log_table.removeRow(500)

    def load_recent_logs(self):
        if hasattr(self.db, "get_recent_log_records"):
            logs = self.db.get_recent_log_records(limit=500)
        else:
            logs = []
            for log in self.db.get_recent_logs(limit=500):
                logs.append(
                    {
                        "timestamp": log[0],
                        "source": "刷卡",
                        "source_detail": log[1],
                        "class_type": None,
                        "class_name": log[2],
                        "status": log[3],
                    }
                )
        for log in reversed(logs):
            timestamp = format_log_timestamp(log["timestamp"])
            
            full_status = log["status"]
            action = full_status
            reason = ""
            
            # Simple parse for backward compatibility display
            if "(" in full_status and full_status.endswith(")"):
                parts = full_status.split(" (", 1)
                action = parts[0]
                reason = parts[1][:-1] # remove trailing )
                
            source = log["source"]
            if source == "刷卡" and log["source_detail"]:
                source = f"刷卡 {log['source_detail']}"
            self.add_log(
                timestamp,
                source,
                format_class_type_label(log.get("class_type")),
                log["class_name"],
                action,
                reason,
            )

    def update_status_bar(self):
        # Update Time Window Display
        schedules = self.config.get("schedules")
        window_text = format_grouped_window_label(
            schedules,
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
        )

        self.window_label.setText(format_schedule_status_html(window_text))

        # Update Status
        if self.config.get("test_mode", False):
             self.status_label.setText("当前状态: [测试模式] 任意时间仅播报，不推送")
             self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        elif self.broadcast_manager.is_within_time_window(class_type=1) or self.broadcast_manager.is_within_time_window(class_type=2):
             states = []
             for class_type in (1, 2):
                 state = "监测中" if self.broadcast_manager.is_within_time_window(class_type=class_type) else "待机"
                 states.append(f"{format_class_type_label(class_type)}{state}")
             self.status_label.setText("当前状态: " + " / ".join(states))
             self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
             self.status_label.setText("当前状态: [待机] 非播报时段")
             self.status_label.setStyleSheet("color: gray;")
