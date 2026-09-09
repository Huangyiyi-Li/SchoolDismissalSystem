import time
from PyQt6.QtCore import QObject, pyqtSignal
from .legacy_udp_reader import LegacyUdpReader
from .uhf_tcp_reader import UhfTcpReader
from .uhf_udp_reader import UhfUdpReader


def reader_settings(config):
    saved = config.get('readers')
    if saved is not None:
        return saved
    return [dict(id='near-reader-1', type='legacy_udp', enabled=True,
                 listenPort=config.get('udp_port', 39169)),
            dict(id='uhf-reader-1', type='uhf_tcp', enabled=False,
                 listenPort=7000, tagCooldownSeconds=3)]


class ReaderManager(QObject):
    credential_received = pyqtSignal(object)
    credential_observed = pyqtSignal(object)
    status_changed = pyqtSignal(str)

    def __init__(self, config, db=None):
        super().__init__()
        self.config, self.db = config, db
        self.readers = []
        self.history = {}
        self.statuses = []
        self.capturing = False

    def _receive(self, event, cooldown):
        self.credential_observed.emit(event)
        if self.capturing and event.credential_type == 'uhf_epc':
            return
        if event.credential_type == 'uhf_epc':
            now = time.monotonic()
            self.history = {k: t for k, t in self.history.items() if now - t < 255}
            key = (event.reader_id, event.credential_id)
            if now - self.history.get(key, float('-inf')) < cooldown:
                return
            self.history[key] = now
        self.credential_received.emit(event)

    def start(self):
        self.statuses = []
        ok = True
        seen = set()
        for settings in reader_settings(self.config):
            if not settings.get('enabled', True):
                continue
            try:
                reader_id = settings['id']
                if not reader_id or reader_id in seen:
                    raise ValueError('读卡器名称重复或为空')
                seen.add(reader_id)
                if not 1 <= int(settings['listenPort']) <= 65535:
                    raise ValueError('端口必须在 1–65535 之间')
                cls = {'legacy_udp': LegacyUdpReader, 'uhf_tcp': UhfTcpReader,
                       'uhf_udp': UhfUdpReader}[settings['type']]
                cooldown = float(settings.get('tagCooldownSeconds', 3))
                if not 0 <= cooldown <= 255:
                    raise ValueError('防抖时间必须在 0–255 秒之间')
                reader = cls(settings, self.db)
                reader.credential_received.connect(lambda event, c=cooldown: self._receive(event, c))
                if hasattr(reader, 'status_changed'):
                    reader.status_changed.connect(self.status_changed.emit)
                self.readers.append(reader)
                started = reader.start()
                ok = started and ok
                message = f"{reader_id}：{'正在监听' if started else '启动失败，端口可能被占用'} {settings['listenPort']}"
            except (KeyError, TypeError, ValueError) as exc:
                ok = False
                message = f'读卡设备配置错误：{exc}'
            self.statuses.append(message)
            self.status_changed.emit(message)
        return ok

    def stop(self):
        for reader in self.readers:
            reader.stop()
            reader.deleteLater()
        self.readers.clear()
        self.history.clear()

    def restart(self):
        self.stop()
        return self.start()
