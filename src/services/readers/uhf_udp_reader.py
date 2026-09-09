from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QUdpSocket, QHostAddress
from .base import CredentialEvent
from .uhf_protocol import StreamParser, parse_frame


class UhfUdpReader(QObject):
    credential_received = pyqtSignal(object)

    def __init__(self, settings, db=None):
        super().__init__()
        self.settings = settings
        self.socket = QUdpSocket(self)
        self.socket.readyRead.connect(self._read)

    def start(self):
        return self.socket.bind(QHostAddress.SpecialAddress.AnyIPv4, int(self.settings['listenPort']))

    def _read(self):
        while self.socket.hasPendingDatagrams():
            data, host, _ = self.socket.readDatagram(self.socket.pendingDatagramSize())
            # Datagram boundaries are independent; never join different senders.
            for frame in StreamParser().feed(data):
                self.credential_received.emit(CredentialEvent(
                    parse_frame(frame), 'uhf_epc', self.settings['id'], host.toString(),
                    'udp', datetime.now().astimezone(), frame))

    def stop(self):
        self.socket.close()
