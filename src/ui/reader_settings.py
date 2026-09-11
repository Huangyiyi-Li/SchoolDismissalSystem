"""Reader setup and local EPC binding; all binding actions are explicit."""
import sqlite3
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QCheckBox,
    QSpinBox, QComboBox, QLabel, QLineEdit, QPushButton, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QGroupBox)
from ..services.readers.reader_manager import reader_settings


class ReaderSettings(QWidget):
    def __init__(self, config, db=None, manager=None, parent=None):
        super().__init__(parent)
        self.config, self.db, self.manager = config, db, manager
        settings = reader_settings(config)
        self.original = settings
        near = next((r for r in settings if r['type'] == 'legacy_udp'), {})
        uhf = next((r for r in settings if r['type'] in ('uhf_tcp', 'uhf_udp')), {})
        self.near_id = near.get('id', 'near-reader-1')
        self.uhf_id = uhf.get('id', 'uhf-reader-1')
        layout = QVBoxLayout(self)
        group = QGroupBox('设备接入')
        form = QFormLayout(group)
        self.near_enabled = QCheckBox('启用近距离刷卡器')
        self.near_enabled.setChecked(near.get('enabled', True))
        form.addRow(self.near_enabled)
        self.near_port = QLineEdit(str(near.get('listenPort', 39169)))
        form.addRow('近距离端口', self.near_port)
        self.uhf_enabled = QCheckBox('启用超高频读卡器')
        self.uhf_enabled.setChecked(uhf.get('enabled', False))
        form.addRow(self.uhf_enabled)
        self.transport = QComboBox()
        self.transport.addItem('TCP（推荐）', 'uhf_tcp')
        self.transport.addItem('UDP', 'uhf_udp')
        self.transport.setCurrentIndex(max(0, self.transport.findData(uhf.get('type', 'uhf_tcp'))))
        form.addRow('连接方式', self.transport)
        self.uhf_port = QSpinBox(); self.uhf_port.setRange(1, 65535)
        self.uhf_port.setValue(int(uhf.get('listenPort', 7000)))
        form.addRow('超高频端口', self.uhf_port)
        self.cooldown = QSpinBox(); self.cooldown.setRange(0, 255); self.cooldown.setSuffix(' 秒')
        self.cooldown.setValue(int(uhf.get('tagCooldownSeconds', 3)))
        form.addRow('同一标签读取间隔', self.cooldown)
        for control in (self.transport, self.uhf_port, self.cooldown):
            control.setEnabled(self.uhf_enabled.isChecked())
            self.uhf_enabled.toggled.connect(control.setEnabled)
        self.near_port.setEnabled(self.near_enabled.isChecked())
        self.near_enabled.toggled.connect(self.near_port.setEnabled)
        hint = QLabel('请用厂家软件将设备设为：主动模式、6C、单张查询（05）。\n目标填写本机 IP 和上方端口。保存后开始监听；未连接设备时可用模拟工具测试。')
        hint.setWordWrap(True); form.addRow(hint)
        self.status = QLabel('\n'.join(manager.statuses) if manager else '尚未启动设备服务')
        self.status.setWordWrap(True); form.addRow(self.status)
        layout.addWidget(group)
        binding = QGroupBox('超高频标签绑定')
        bf = QVBoxLayout(binding)
        bf.addWidget(QLabel('4 字节标签自动转十进制匹配当前学校卡号；也可采集后手工绑定，手工绑定优先。'))
        self.capture = QPushButton('开始采集标签'); self.capture.setCheckable(True)
        self.capture.toggled.connect(self._capture)
        bf.addWidget(self.capture)
        self.epc = QLineEdit(); self.epc.setPlaceholderText('待采集，或粘贴标签编号')
        bf.addWidget(self.epc)
        self.classes = QComboBox()
        self.classes.addItem('请选择班级及原有卡号', None)
        if db:
            for card, kind, class_id, name, school in db.get_all_mappings():
                if str(school) == str(config.get('school_id')):
                    self.classes.addItem(f'{name} · {"社团班" if kind == 2 else "行政班"} · {card}', card)
        bf.addWidget(self.classes)
        actions = QHBoxLayout()
        bind = QPushButton('绑定标签'); bind.clicked.connect(self._bind); actions.addWidget(bind)
        remove = QPushButton('解除选中绑定'); remove.clicked.connect(self._remove); actions.addWidget(remove)
        bf.addLayout(actions)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['标签编号', '原有卡号', '班级'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        bf.addWidget(self.table)
        layout.addWidget(binding)
        layout.addStretch()
        self.capture.setEnabled(manager is not None)
        bind.setEnabled(db is not None); remove.setEnabled(db is not None)
        if manager:
            manager.credential_observed.connect(self._observed)
            manager.status_changed.connect(self.status.setText)
        self.refresh()

    def values(self):
        port = int(self.near_port.text())
        if not 1 <= port <= 65535:
            raise ValueError('近距离端口应为 1–65535')
        if self.near_enabled.isChecked() and self.uhf_enabled.isChecked() and self.transport.currentData() == 'uhf_udp' and port == self.uhf_port.value():
            raise ValueError('两种 UDP 读卡器不能使用同一个端口')
        owned = {self.near_id, self.uhf_id}
        return [r for r in self.original if r['id'] not in owned] + [
            dict(id=self.near_id, type='legacy_udp', enabled=self.near_enabled.isChecked(), listenPort=port),
            dict(id=self.uhf_id, type=self.transport.currentData(), enabled=self.uhf_enabled.isChecked(),
                 listenPort=self.uhf_port.value(), tagCooldownSeconds=self.cooldown.value())]

    def _capture(self, checked):
        if self.manager:
            self.manager.capturing = checked
        self.capture.setText('停止采集（采集中不触发放学）' if checked else '开始采集标签')

    def _observed(self, event):
        if self.capture.isChecked() and event.credential_type == 'uhf_epc':
            self.epc.setText(event.credential_id)
            self.status.setText(f'已采集标签，来自 {event.reader_ip}；请选择班级并绑定')

    def _bind(self):
        try:
            if not self.classes.currentData():
                raise ValueError('请先选择班级；没有班级时请先同步学校数据')
            self.db.bind_credential(self.config.get('school_id'), self.epc.text(), self.classes.currentData())
        except (ValueError, sqlite3.IntegrityError) as exc:
            QMessageBox.warning(self, '无法绑定', '该标签已绑定，请先解除原绑定' if isinstance(exc, sqlite3.IntegrityError) else str(exc))
            return
        self.refresh()
        self.status.setText('标签绑定已保存。停止采集后再次读卡，即可按放学规则处理。')

    def _remove(self):
        row = self.table.currentRow()
        if row < 0:
            return
        epc = self.table.item(row, 0).text()
        if QMessageBox.question(self, '解除绑定', f'确定解除标签 {epc} 的绑定？') == QMessageBox.StandardButton.Yes:
            self.db.delete_credential(self.config.get('school_id'), epc)
            self.refresh()

    def refresh(self):
        rows = self.db.list_credentials(self.config.get('school_id')) if self.db else []
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, max(280, self.table.columnWidth(0)))

    def cleanup(self):
        self.capture.setChecked(False)
        if self.manager:
            for signal, slot in [(self.manager.credential_observed, self._observed),
                                 (self.manager.status_changed, self.status.setText)]:
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
