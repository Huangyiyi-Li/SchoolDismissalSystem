from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QTcpServer, QHostAddress
from .base import CredentialEvent
from .uhf_protocol import StreamParser, parse_frame


class UhfTcpReader(QObject):
    credential_received = pyqtSignal(object)
    status_changed = pyqtSignal(str)

    def __init__(self, settings, db=None):
        super().__init__()
        self.settings = settings
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._accept)
        self.clients = {}

    def start(self):
        return self.server.listen(QHostAddress.SpecialAddress.AnyIPv4, int(self.settings['listenPort']))

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if len(self.clients) >= 32:
                socket.abort(); socket.deleteLater(); continue
            socket.setReadBufferSize(65536)
            self.clients[socket] = StreamParser()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._disconnect(s))
            self.status_changed.emit(f"{self.settings['id']}：读卡器已连接 {socket.peerAddress().toString()}")
            self._read(socket)

    def _read(self, socket):
        parser = self.clients.get(socket)
        if parser is None:
            return
        for frame in parser.feed(bytes(socket.readAll())):
            self.credential_received.emit(CredentialEvent(
                parse_frame(frame), 'uhf_epc', self.settings['id'],
                socket.peerAddress().toString(), 'tcp', datetime.now().astimezone(), frame))

    def _disconnect(self, socket):
        self.clients.pop(socket, None)
        self.status_changed.emit(f"{self.settings['id']}：读卡器已断开")
        socket.deleteLater()

    def stop(self):
        self.server.close()
        for socket in list(self.clients):
            socket.abort()
        self.clients.clear()
