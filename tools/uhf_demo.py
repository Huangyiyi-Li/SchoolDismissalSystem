"""Isolated, synthetic-data trial. No school API, MQTT or physical LED writes."""
import sys
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QPlainTextEdit
from src.services.config_manager import ConfigManager
from src.database import DatabaseManager
from src.services.readers.reader_manager import ReaderManager
from src.services.readers.uhf_protocol import encode_epc
from src.services.broadcast_manager import BroadcastManager
from src.services.led_service import LedService
from src.services.led_bridge_client import BridgeResult
from src.ui.settings_dialog import SettingsDialog


class DemoLedBridge:
    def ping(self, *args, **kwargs):
        return BridgeResult(False, '模拟试用不连接实体 LED；请使用本地预览')

    display = ping
    clear = ping

    def shutdown(self):
        pass


def main():
    app = QApplication(sys.argv)
    with TemporaryDirectory(prefix='uhf-demo-') as directory:
        config = ConfigManager(str(Path(directory) / 'settings.json'))
        config.set('school_id', 'DEMO')
        config.set('test_mode', True)
        config.set('tts_repeat_count', 1)
        config.set('led_enabled', False)
        # Reserve a free local test port, without altering production configuration.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        config.set('readers', [dict(id='demo-uhf', type='uhf_tcp', enabled=True,
                    listenPort=port, tagCooldownSeconds=3)])
        db = DatabaseManager(str(Path(directory) / 'school.db'))
        for i in range(1, 4):
            db.add_mapping(f'900{i}', f'一年级{i}班', f'c{i}', 'DEMO', 1)
            db.upsert_led_class('DEMO', 1, f'c{i}', '一年级', f'{i}班', source_order=i)
        epc = '3005FB63AC1F3841EC880467'
        db.bind_credential('DEMO', epc, '9001')
        led = LedService(config, db, bridge=DemoLedBridge(), output_dir=Path(directory) / 'led')
        business = BroadcastManager(config, db, led_service=led)
        readers = ReaderManager(config, db)
        readers.credential_received.connect(business.process_credential)
        window = QWidget(); window.setWindowTitle('超高频测试版 · 模拟数据'); window.resize(820, 520)
        layout = QVBoxLayout(window)
        layout.addWidget(QLabel('本窗口使用临时学校、班级和标签数据，不向后台或实体 LED 发送。\n关闭后清除试用数据；真实学校设置不受影响。'))
        layout.addWidget(QLabel(f'示例标签已绑定一年级1班：{epc}'))
        log = QPlainTextEdit(); log.setReadOnly(True)
        settings = QPushButton('打开新版系统设置')
        window.settings_dialog = None
        def open_settings():
            if window.settings_dialog is not None and window.settings_dialog.isVisible():
                window.settings_dialog.raise_()
                return
            dialog = SettingsDialog(config, SimpleNamespace(db=db, api=None), led, window,
                                    reader_manager=readers)
            window.settings_dialog = dialog
            dialog.show()
        settings.clicked.connect(open_settings); layout.addWidget(settings)
        send = QPushButton('模拟读到标签（可连续点击测试去重）')
        def simulate():
            target = next((r for r in readers.readers if hasattr(r, 'server')), None)
            if target is None:
                log.appendPlainText('请先启用 TCP 超高频读卡器'); return
            try:
                with socket.create_connection(('127.0.0.1', target.server.serverPort()), timeout=2) as conn:
                    conn.sendall(encode_epc(epc))
            except OSError as exc:
                log.appendPlainText(str(exc))
        send.clicked.connect(simulate); layout.addWidget(send)
        reset = QPushButton('清除本次播报记录，重新试一次')
        def reset_history():
            readers.history.clear(); business.voice_history.clear(); business.api_push_history.clear()
            log.appendPlainText('模拟记录已清除，可再次测试播报')
        reset.clicked.connect(reset_history); layout.addWidget(reset)
        layout.addWidget(log)
        business.log_updated.connect(lambda *parts: log.appendPlainText(' | '.join(parts)))
        readers.status_changed.connect(log.appendPlainText)
        readers.start(); window.show()
        app.exec()
        readers.stop(); business.cleanup(); led.shutdown()


if __name__ == '__main__':
    main()
