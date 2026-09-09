from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from ..udp_server import UDPServerService
from .base import CredentialEvent


class LegacyUdpReader(QObject):
    credential_received = pyqtSignal(object)

    def __init__(self, settings, db=None):
        super().__init__()
        self.reader_id = settings['id']
        self.service = UDPServerService(port=int(settings['listenPort']), db_manager=db)
        self.service.card_swiped.connect(self._received)

    def _received(self, card, ip):
        self.credential_received.emit(CredentialEvent(
            card, 'legacy_card', self.reader_id, ip, 'udp', datetime.now().astimezone()))

    def start(self):
        return self.service.start()

    def stop(self):
        self.service.stop()
