from __future__ import annotations

import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
)

from src.services.dismissal_window import format_window_label
from src.services.system_status import RuntimeStatusStore
from .dashboard_presenter import DashboardPresenter
from .dashboard_view import DashboardView
from .maintenance_panel import MaintenancePanel
from .maintenance_session import MaintenanceSessionController


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_manager,
        db_manager,
        broadcast_manager,
        udp_server,
        data_sync_service=None,
        status_store=None,
    ):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.broadcast_manager = broadcast_manager
        self.udp_server = udp_server
        self.data_sync_service = data_sync_service
        self.status_store = (
            status_store
            or getattr(self.broadcast_manager, "status_store", None)
            or RuntimeStatusStore()
        )

        self.presenter = DashboardPresenter()
        self.maintenance_session = MaintenanceSessionController(
            pin=self.config.get("maintenance_pin", "1234"),
            timeout_seconds=self.config.get("maintenance_timeout_seconds", 300),
        )
        self.current_mode = "guard"
        self._device_status_map: dict[str, str] = {}

        self.setWindowTitle("校园放学守护看板")
        self.resize(1200, 800)

        self._setup_ui()
        self._apply_window_styles()
        self._connect_signals()
        self._setup_shortcuts()
        self._setup_timers()

        self.load_recent_logs()
        self.enter_guard_mode()
        self._refresh_dashboard()

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("mainShell")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        self.mode_stack = QStackedWidget()
        root_layout.addWidget(self.mode_stack)

        self.dashboard_view = DashboardView(self)
        self.maintenance_panel = MaintenancePanel(self)

        self.mode_stack.addWidget(self.dashboard_view)
        self.mode_stack.addWidget(self.maintenance_panel)

        self.maintenance_panel.open_settings.connect(self._open_settings_from_maintenance)
        self.maintenance_panel.open_schedule.connect(self._open_schedule_from_maintenance)
        self.maintenance_panel.open_device_manager.connect(self._open_device_manager_from_maintenance)
        self.maintenance_panel.open_mapping.connect(self._open_mapping_from_maintenance)
        self.maintenance_panel.force_sync.connect(self._force_sync_from_maintenance)
        self.maintenance_panel.exit_maintenance.connect(self.enter_guard_mode)
        self.maintenance_panel.test_mode_changed.connect(self._set_test_mode)

    def _apply_window_styles(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #07111d;
            }
            QWidget#mainShell {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #07111d, stop:0.55 #091423, stop:1 #0b1930);
            }
            QInputDialog, QMessageBox {
                background: #0d1829;
            }
            """
        )

    def _connect_signals(self):
        self.udp_server.card_swiped.connect(self.broadcast_manager.process_swipe)
        self.udp_server.device_updated.connect(self.update_device_status)
        self.broadcast_manager.log_updated.connect(self.add_log)

    def _setup_shortcuts(self):
        self._maintenance_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self._maintenance_shortcut.activated.connect(self.request_maintenance_mode)

    def _setup_timers(self):
        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.timeout.connect(self._refresh_dashboard)
        self.dashboard_timer.start(1000)

        self.maintenance_relock_timer = QTimer(self)
        self.maintenance_relock_timer.timeout.connect(self._check_maintenance_timeout)
        self.maintenance_relock_timer.start(1000)

    def enter_guard_mode(self):
        self.current_mode = "guard"
        self.mode_stack.setCurrentWidget(self.dashboard_view)

    def enter_maintenance_mode(self):
        self.current_mode = "maintenance"
        self.touch_maintenance_session()
        self.maintenance_panel.set_test_mode(self.config.get("test_mode", False))
        self.mode_stack.setCurrentWidget(self.maintenance_panel)

    def request_maintenance_mode(self):
        if self.maintenance_session.is_unlocked():
            self.enter_maintenance_mode()
            return

        attempt, ok = QInputDialog.getText(
            self,
            "维护模式",
            "请输入维护 PIN:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return

        if self.maintenance_session.unlock(attempt):
            self.enter_maintenance_mode()
        else:
            QMessageBox.warning(self, "拒绝访问", "PIN 错误，无法进入维护模式。")
            self.enter_guard_mode()

    def touch_maintenance_session(self):
        self.maintenance_session.touch()

    def require_maintenance_access(self, action_label="维护操作", interactive=True):
        if not self.maintenance_session.is_unlocked():
            self.enter_guard_mode()
            if interactive:
                QMessageBox.warning(self, "维护会话已锁定", f"{action_label}失败：维护会话已过期。")
            return False
        self.touch_maintenance_session()
        return True

    def _check_maintenance_timeout(self):
        if self.current_mode == "maintenance" and not self.maintenance_session.is_unlocked():
            self.enter_guard_mode()

    def _online_devices_count(self) -> int:
        devices = getattr(self.udp_server, "devices", None)
        if isinstance(devices, dict):
            now = datetime.datetime.now()
            return sum(
                1
                for last_seen in devices.values()
                if isinstance(last_seen, datetime.datetime)
                and (now - last_seen).total_seconds() <= 60
            )
        return sum(1 for status in self._device_status_map.values() if status == "在线")

    def _refresh_dashboard(self):
        if hasattr(self.udp_server, "check_offline_devices"):
            try:
                self.udp_server.check_offline_devices()
            except Exception:
                pass

        snapshot = self.status_store.snapshot()
        window_label = format_window_label(
            self.config.get("schedules"),
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
        )
        vm = self.presenter.build(
            snapshot=snapshot,
            online_devices=self._online_devices_count(),
            window_label=window_label,
        )

        self.dashboard_view.set_banner(vm.banner_text, vm.should_pulse)
        self.dashboard_view.set_clock_text(datetime.datetime.now().strftime("%H:%M:%S"))
        self.dashboard_view.set_devices_text(vm.online_devices_text)
        self.dashboard_view.set_window_text(vm.window_label)
        self.dashboard_view.set_runtime_text(
            f"运行状态: {vm.overall_level.name} / {snapshot.primary_alert.summary}"
        )

    def update_device_status(self, ip, time_str, status, name=None):
        self._device_status_map[ip] = status
        self._refresh_dashboard()

    def add_log(self, time_str, card_id, class_name, action, reason=""):
        self.dashboard_view.add_log_row(time_str, card_id, class_name, action, reason)

    def load_recent_logs(self):
        logs = self.db.get_recent_logs()
        for log in logs:
            try:
                dt = log[0].split(" ")[1]
            except Exception:
                dt = str(log[0])

            full_status = log[3]
            action = full_status
            reason = ""
            if "(" in full_status and full_status.endswith(")"):
                parts = full_status.split(" (", 1)
                action = parts[0]
                reason = parts[1][:-1]
            self.add_log(dt, log[1], log[2], action, reason)

    def open_mapping_dialog(self):
        from .mapping_dialog import MappingDialog

        if not self.require_maintenance_access("打开卡号映射"):
            return
        dialog = MappingDialog(self.db, self)
        dialog.exec()

    def open_settings_dialog(self):
        from .settings_dialog import SettingsDialog

        if not self.require_maintenance_access("打开学校设置"):
            return
        dialog = SettingsDialog(self.config, self.data_sync_service, self)
        dialog.exec()

    def open_schedule_dialog(self):
        from .schedule_dialog import ScheduleDialog

        if not self.require_maintenance_access("打开放学时间"):
            return
        dialog = ScheduleDialog(self.config, self)
        dialog.exec()

    def open_device_manager(self):
        from .device_manager_dialog import DeviceManagerDialog

        if not self.require_maintenance_access("打开设备管理"):
            return
        dialog = DeviceManagerDialog(self.db, self)
        dialog.exec()

    def _force_sync_data(self):
        if not self.require_maintenance_access("执行立即同步"):
            return
        if self.data_sync_service and hasattr(self.data_sync_service, "force_sync"):
            self.data_sync_service.force_sync()

    def _set_test_mode(self, enabled: bool):
        if not self.require_maintenance_access("切换测试模式"):
            self.maintenance_panel.set_test_mode(self.config.get("test_mode", False))
            return
        self.config.set("test_mode", bool(enabled))
        self.config.save()
        self._refresh_dashboard()

    def _open_settings_from_maintenance(self):
        self.open_settings_dialog()

    def _open_schedule_from_maintenance(self):
        self.open_schedule_dialog()

    def _open_device_manager_from_maintenance(self):
        self.open_device_manager()

    def _open_mapping_from_maintenance(self):
        self.open_mapping_dialog()

    def _force_sync_from_maintenance(self):
        self._force_sync_data()
