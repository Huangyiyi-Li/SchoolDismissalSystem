from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..services.device_network_service import (
    DEFAULT_DEVICE_COMMAND_PORT,
    DeviceNetworkError,
    DeviceNetworkProfile,
    DeviceNetworkService,
)

LOGGER = logging.getLogger(__name__)


class _DiscoveryWorker(QObject):
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        network_service: DeviceNetworkService,
        action: str,
        *,
        exclude_paths: list[str] | None = None,
        allow_subnet_scan: bool = True,
    ):
        super().__init__()
        self.network_service = network_service
        self.action = action
        self.exclude_paths = exclude_paths or []
        self.allow_subnet_scan = allow_subnet_scan

    @pyqtSlot()
    def run(self):
        try:
            entries = self.network_service.discover_devices(
                exclude_paths=self.exclude_paths,
                allow_subnet_scan=self.allow_subnet_scan,
            )
        except DeviceNetworkError as exc:
            self.failed.emit(self.action, str(exc))
            return
        except Exception as exc:
            LOGGER.exception("Unexpected reader discovery failure")
            self.failed.emit(self.action, str(exc))
            return

        self.finished.emit(self.action, entries)


class DeviceNetworkDialog(QDialog):
    def __init__(
        self,
        network_service: DeviceNetworkService,
        current_ip: str = "",
        current_name: str = "",
        occupied_ips: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.network_service = network_service
        self.current_name = current_name or current_ip or "设备"
        self.current_ip = current_ip
        self.occupied_ips = occupied_ips or []
        self._baseline_paths: list[str] = []
        self._baseline_recorded = False
        self._discovery_thread: QThread | None = None
        self._discovery_worker: _DiscoveryWorker | None = None

        self.setWindowTitle(f"配置刷卡器网络 - {self.current_name}")
        self.resize(640, 520)
        self._setup_ui()
        self._apply_initial_state()

    def _touch_parent(self):
        parent = self.parent()
        if parent and hasattr(parent, "touch_maintenance_session"):
            parent.touch_maintenance_session()

    def _require_parent_access(self, action_label: str) -> bool:
        parent = self.parent()
        if parent and hasattr(parent, "require_maintenance_access"):
            return parent.require_maintenance_access(action_label)
        return True

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        intro = QLabel(
            "支持自动生成固定网络参数，也支持手动写入学校指定 IP。"
            "如果刷卡器还没出现在设备列表里，也可以直接从这里开始查找或手动输入当前 IP。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.notice_label = QLabel(
            "说明: DHCP 开关目前未在公开 SDK 中暴露，如现场必须切 DHCP，请暂时使用厂家工具。"
        )
        self.notice_label.setWordWrap(True)
        self.notice_label.setProperty("muted", True)
        layout.addWidget(self.notice_label)

        source_group = QGroupBox("连接目标")
        source_form = QFormLayout(source_group)

        source_row = QHBoxLayout()
        self.discovery_combo = QComboBox()
        self.discovery_combo.addItem("手动输入当前设备地址", "")
        self.discovery_combo.currentIndexChanged.connect(self._on_discovery_changed)
        source_row.addWidget(self.discovery_combo, 1)

        self.scan_btn = QPushButton("扫描当前在线刷卡器")
        self.scan_btn.clicked.connect(self.scan_current_devices)
        source_row.addWidget(self.scan_btn)
        source_form.addRow("设备来源:", source_row)

        helper_row = QHBoxLayout()
        self.snapshot_btn = QPushButton("记录当前网络状态")
        self.snapshot_btn.clicked.connect(self.capture_baseline)
        helper_row.addWidget(self.snapshot_btn)

        self.new_device_btn = QPushButton("查找新接入刷卡器")
        self.new_device_btn.clicked.connect(self.find_new_devices)
        helper_row.addWidget(self.new_device_btn)
        source_form.addRow("", helper_row)

        self.discovery_hint = QLabel(
            "建议现场流程: 先记录当前网络状态，再接入新刷卡器，最后点击“查找新接入刷卡器”。"
        )
        self.discovery_hint.setWordWrap(True)
        self.discovery_hint.setProperty("muted", True)
        source_form.addRow("", self.discovery_hint)

        self.current_ip_edit = QLineEdit(self.current_ip)
        self.current_ip_edit.setPlaceholderText("当前设备 IP，例如 192.168.1.80")
        source_form.addRow("当前设备 IP:", self.current_ip_edit)

        self.current_port_spin = QSpinBox()
        self.current_port_spin.setRange(1, 65535)
        self.current_port_spin.setValue(self.network_service.command_port or DEFAULT_DEVICE_COMMAND_PORT)
        source_form.addRow("当前命令端口:", self.current_port_spin)

        source_btn_row = QHBoxLayout()
        self.suggest_btn = QPushButton("生成推荐配置")
        self.suggest_btn.clicked.connect(self.fill_suggestion)
        source_btn_row.addWidget(self.suggest_btn)

        self.read_btn = QPushButton("读取当前配置")
        self.read_btn.clicked.connect(self.read_current_profile)
        source_btn_row.addWidget(self.read_btn)
        source_form.addRow("", source_btn_row)

        layout.addWidget(source_group)

        config_group = QGroupBox("目标网络参数")
        config_form = QFormLayout(config_group)

        self.local_ip_edit = QLineEdit()
        config_form.addRow("固定 IP:", self.local_ip_edit)

        self.mask_edit = QLineEdit()
        self.mask_edit.setPlaceholderText("255.255.255.0")
        config_form.addRow("子网掩码:", self.mask_edit)

        self.gateway_edit = QLineEdit()
        config_form.addRow("网关:", self.gateway_edit)

        self.server_ip_edit = QLineEdit()
        self.server_ip_edit.setPlaceholderText("值守主机的 IP")
        config_form.addRow("主机 IP:", self.server_ip_edit)

        self.server_port_spin = QSpinBox()
        self.server_port_spin.setRange(1, 65535)
        self.server_port_spin.setValue(int(self.network_service.config.get("udp_port", 39169)) if self.network_service.config else 39169)
        config_form.addRow("主机端口:", self.server_port_spin)

        self.local_port_spin = QSpinBox()
        self.local_port_spin.setRange(1, 65535)
        self.local_port_spin.setValue(self.current_port_spin.value())
        config_form.addRow("设备本地端口:", self.local_port_spin)

        layout.addWidget(config_group)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.apply_btn = QPushButton("写入配置并重启设备")
        self.apply_btn.clicked.connect(self.apply_profile)
        button_row.addWidget(self.apply_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def _apply_initial_state(self):
        if not self.network_service.is_available:
            self.notice_label.setText(self.network_service.availability_reason or "网络配置组件不可用。")
            self.scan_btn.setEnabled(False)
            self.snapshot_btn.setEnabled(False)
            self.new_device_btn.setEnabled(False)
            self.read_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
        else:
            self.fill_suggestion()

    def _selected_device_path(self) -> str | None:
        value = self.discovery_combo.currentData()
        return value if value else None

    def _on_discovery_changed(self):
        path = self._selected_device_path()
        if not path:
            return
        if ":" in path:
            host, _, port_text = path.rpartition(":")
            self.current_ip_edit.setText(host)
            if port_text.isdigit():
                self.current_port_spin.setValue(int(port_text))
                self.local_port_spin.setValue(int(port_text))

    def fill_suggestion(self):
        try:
            profile = self.network_service.suggest_profile(
                current_ip=self.current_ip_edit.text().strip() or None,
                occupied_ips=self.occupied_ips,
                local_port=self.current_port_spin.value(),
            )
        except DeviceNetworkError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return

        self._apply_profile_to_form(profile)

    def _apply_profile_to_form(self, profile: DeviceNetworkProfile):
        self.local_ip_edit.setText(profile.local_ip)
        self.mask_edit.setText(profile.subnet_mask)
        self.gateway_edit.setText(profile.gateway)
        self.server_ip_edit.setText(profile.server_ip)
        self.server_port_spin.setValue(profile.server_port)
        self.local_port_spin.setValue(profile.local_port)

    def _refresh_discovery_combo(self, entries):
        self.discovery_combo.clear()
        self.discovery_combo.addItem("手动输入当前设备地址", "")
        for entry in entries:
            self.discovery_combo.addItem(entry.label, entry.path)

        if entries:
            self.discovery_combo.setCurrentIndex(1)

    def _set_discovery_busy(self, busy: bool, hint_text: str = ""):
        self.scan_btn.setEnabled(not busy and self.network_service.is_available)
        self.snapshot_btn.setEnabled(not busy and self.network_service.is_available)
        self.new_device_btn.setEnabled(not busy and self.network_service.is_available)
        if hint_text:
            self.discovery_hint.setText(hint_text)

    def _start_discovery(
        self,
        action: str,
        *,
        allow_subnet_scan: bool,
        exclude_paths: list[str] | None,
        hint_text: str,
    ):
        if self._discovery_thread is not None:
            return
        if not self._require_parent_access("搜索可配置设备"):
            self.close()
            return

        self._touch_parent()
        self._set_discovery_busy(True, hint_text)

        self._discovery_thread = QThread(self)
        self._discovery_worker = _DiscoveryWorker(
            self.network_service,
            action,
            exclude_paths=exclude_paths,
            allow_subnet_scan=allow_subnet_scan,
        )
        self._discovery_worker.moveToThread(self._discovery_thread)
        self._discovery_thread.started.connect(self._discovery_worker.run)
        self._discovery_worker.finished.connect(self._handle_discovery_finished)
        self._discovery_worker.failed.connect(self._handle_discovery_failed)
        self._discovery_worker.finished.connect(self._cleanup_discovery_thread)
        self._discovery_worker.failed.connect(self._cleanup_discovery_thread)
        self._discovery_thread.start()

    def _cleanup_discovery_thread(self, *_args):
        if self._discovery_thread is None:
            return
        self._discovery_thread.quit()
        self._discovery_thread.wait()
        if self._discovery_worker is not None:
            self._discovery_worker.deleteLater()
        self._discovery_thread.deleteLater()
        self._discovery_worker = None
        self._discovery_thread = None
        self._set_discovery_busy(False)

    def _handle_discovery_finished(self, action: str, entries):
        if action == "baseline":
            self._baseline_paths = [entry.path for entry in entries]
            self._baseline_recorded = True
            self.discovery_hint.setText(
                f"已记录当前网络状态，当前识别到 {len(entries)} 台刷卡器。"
                " 现在接入新刷卡器后，点击“查找新接入刷卡器”。"
            )
            QMessageBox.information(
                self,
                "已记录当前状态",
                f"当前已确认 {len(entries)} 台刷卡器。\n\n"
                "请现在接入或上电新的刷卡器，然后点击“查找新接入刷卡器”。",
            )
            return

        self._refresh_discovery_combo(entries)
        if action == "scan":
            if not entries:
                QMessageBox.information(
                    self,
                    "搜索完成",
                    "没有发现能直接读取网络配置的刷卡器。\n\n"
                    "你仍然可以手动输入当前设备 IP 和端口继续配置，"
                    "或者先记录当前网络状态，再用“查找新接入刷卡器”缩小范围。",
                )
                return

            self.discovery_hint.setText(f"已发现 {len(entries)} 台已确认刷卡器。")
            QMessageBox.information(self, "搜索完成", f"已发现 {len(entries)} 台已确认刷卡器。")
            return

        if action == "new":
            if entries:
                self.discovery_hint.setText(
                    f"发现 {len(entries)} 台新接入刷卡器候选，列表里只保留了能读取配置的设备。"
                )
                QMessageBox.information(
                    self,
                    "发现新设备",
                    f"发现 {len(entries)} 台新接入刷卡器候选。\n\n"
                    "列表里已经过滤掉无法读取网络配置的普通网络设备。",
                )
                return

            self.discovery_hint.setText(
                "没有找到新接入刷卡器。可以重新记录当前网络状态后再试，"
                "或者直接手动输入刷卡器当前 IP。"
            )
            QMessageBox.information(
                self,
                "未发现新设备",
                "没有找到新接入刷卡器。\n\n"
                "如果设备刚刚接入，请等待几秒再试；"
                "如果仍然没有结果，可以重新记录当前网络状态，或直接手动输入当前 IP。",
            )

    def _handle_discovery_failed(self, action: str, message: str):
        titles = {
            "baseline": "记录失败",
            "scan": "搜索失败",
            "new": "搜索失败",
        }
        self.discovery_hint.setText("设备搜索失败，请检查网络后重试，或改用手动输入当前 IP。")
        QMessageBox.warning(self, titles.get(action, "搜索失败"), message)

    def capture_baseline(self):
        self._start_discovery(
            "baseline",
            allow_subnet_scan=False,
            exclude_paths=None,
            hint_text="正在记录当前网络状态，不会深度扫描整网，请稍候...",
        )

    def scan_current_devices(self):
        self._start_discovery(
            "scan",
            allow_subnet_scan=True,
            exclude_paths=None,
            hint_text="正在扫描当前在线刷卡器，界面保持可操作，请稍候...",
        )

    def find_new_devices(self):
        if not self._baseline_recorded:
            self.capture_baseline()
            return

        self._start_discovery(
            "new",
            allow_subnet_scan=True,
            exclude_paths=self._baseline_paths,
            hint_text="正在查找新接入刷卡器，界面保持可操作，请稍候...",
        )

    def read_current_profile(self):
        if not self._require_parent_access("读取设备网络配置"):
            self.close()
            return
        self._touch_parent()
        try:
            profile = self.network_service.read_profile(
                current_ip=self.current_ip_edit.text().strip() or None,
                current_port=self.current_port_spin.value(),
                device_path=self._selected_device_path(),
            )
        except DeviceNetworkError as exc:
            QMessageBox.warning(self, "读取失败", str(exc))
            return

        self._apply_profile_to_form(profile)
        QMessageBox.information(self, "读取成功", "已读取当前设备的网络配置。")

    def apply_profile(self):
        if not self._require_parent_access("写入设备网络配置"):
            self.close()
            return
        self._touch_parent()
        current_ip = self.current_ip_edit.text().strip()
        if not current_ip and not self._selected_device_path():
            QMessageBox.warning(self, "错误", "请先输入当前设备 IP，或者先搜索并选择可配置设备。")
            return

        try:
            profile = DeviceNetworkProfile(
                local_ip=self.local_ip_edit.text().strip(),
                subnet_mask=self.mask_edit.text().strip(),
                gateway=self.gateway_edit.text().strip(),
                server_ip=self.server_ip_edit.text().strip(),
                server_port=self.server_port_spin.value(),
                local_port=self.local_port_spin.value(),
            )
            self.network_service.apply_profile(
                profile,
                current_ip=current_ip or None,
                current_port=self.current_port_spin.value(),
                device_path=self._selected_device_path(),
            )
        except DeviceNetworkError as exc:
            QMessageBox.warning(self, "写入失败", str(exc))
            return

        QMessageBox.information(
            self,
            "配置完成",
            "网络参数已经写入设备，并已请求设备重启。\n\n"
            f"新的固定 IP: {profile.local_ip}\n"
            f"主机地址: {profile.server_ip}:{profile.server_port}\n\n"
            "设备重启后，请用新的 IP 重新确认在线状态。",
        )
        self.accept()
