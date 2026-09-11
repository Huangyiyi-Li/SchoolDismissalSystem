import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import socket
import time
from datetime import datetime
from unittest.mock import Mock
from PyQt6.QtCore import QCoreApplication
from src.services.readers.reader_manager import ReaderManager
from src.services.readers.uhf_tcp_reader import UhfTcpReader
from src.services.readers.uhf_udp_reader import UhfUdpReader
from src.services.readers.uhf_protocol import encode_epc
from src.services.readers.base import CredentialEvent

EPC = '3005FB63AC1F3841EC880467'

def pump(app):
    for _ in range(20):
        app.processEvents(); time.sleep(.002)

def test_tcp_clients_have_separate_buffers_and_disconnect():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    reader = UhfTcpReader({'id': 'a', 'listenPort': 0})
    received = []; reader.credential_received.connect(received.append)
    assert reader.start()
    target = ('127.0.0.1', reader.server.serverPort())
    a = socket.create_connection(target); b = socket.create_connection(target)
    try:
        frame = encode_epc(EPC)
        a.sendall(frame[:7]); b.sendall(frame); pump(app)
        assert len(received) == 1
        a.sendall(frame[7:] + frame); pump(app)
        assert [e.credential_id for e in received] == [EPC] * 3
    finally:
        a.close(); b.close(); pump(app)
        assert not reader.clients
        reader.stop()

def test_udp_and_legacy_coexist_and_capture_blocks_uhf_only():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    manager = ReaderManager({})
    out = []; seen = []
    manager.credential_received.connect(out.append)
    manager.credential_observed.connect(seen.append)
    event = CredentialEvent(EPC, 'uhf_epc', 'a', '127.0.0.1', 'tcp', datetime.now())
    manager._receive(event, 3); manager._receive(event, 3)
    assert len(out) == 1 and len(seen) == 2
    manager.capturing = True
    manager._receive(event, 0)
    assert len(out) == 1
    legacy = CredentialEvent('123', 'legacy_card', 'b', '127.0.0.1', 'udp', datetime.now())
    manager._receive(legacy, 3)
    assert out[-1].credential_id == '123'
    reader = UhfUdpReader({'id': 'u', 'listenPort': 0})
    assert reader.start()
    udp_out = []; reader.credential_received.connect(udp_out.append)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(encode_epc(EPC), ('127.0.0.1', reader.socket.localPort()))
        pump(app)
    assert udp_out[0].credential_id == EPC
    reader.stop()

def test_legacy_adapter_retains_byte_order_and_sequence_dedup():
    from src.services.readers.legacy_udp_reader import LegacyUdpReader
    reader = LegacyUdpReader({'id': 'near', 'listenPort': 39169})
    out = []; reader.credential_received.connect(out.append)
    frame = bytearray(22); frame[0] = 0xC1; frame[7] = 5
    frame[10:14] = (3651117073).to_bytes(4, 'little')
    reader.service.parse_datagram(frame, '127.0.0.1')
    reader.service.parse_datagram(frame, '127.0.0.1')
    assert len(out) == 1 and out[0].credential_id == '3651117073'

def test_business_resolves_api_card_and_retains_epc_in_log_context():
    from src.services.broadcast_manager import BroadcastManager
    business = Mock()
    business.config.get.return_value = 's1'
    business.db.resolve_credential.return_value = '123'
    event = CredentialEvent(EPC, 'uhf_epc', 'a', '127.0.0.1', 'tcp', datetime.now())
    BroadcastManager.process_credential(business, event)
    args = business._process_card.call_args.args
    assert args[0] == '123' and EPC in args[3]
    business.db.resolve_credential.return_value = None
    business._process_card.reset_mock()
    BroadcastManager.process_credential(business, event)
    business._process_card.assert_not_called()
    business._log_event.assert_called_once()

def test_real_device_frame_through_tcp_manager_to_class_and_api(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QThread
    from src.database import DatabaseManager
    from src.services.broadcast_manager import BroadcastManager
    from threading import Event
    app = QApplication.instance() or QApplication([])
    # Use the real business service, silencing only the system voice worker.
    monkeypatch.setattr(QThread, 'start', lambda self: None)
    config = {'school_id': 's1', 'test_mode': False, 'deduplication_interval_seconds': 300}
    db = DatabaseManager(str(tmp_path / 'school.db'))
    db.add_mapping('2921180939', '一年级一班', 'c1', 's1', 1)
    api = Mock(); pushed = Event()
    api.push_dismissal_notice.side_effect = lambda *a, **kw: pushed.set()
    led = Mock()
    business = BroadcastManager(config, db, api_service=api, led_service=led)
    business.tts_worker.add_text = Mock()
    business.get_current_window_signature = lambda **kw: 'test-window'
    manager = ReaderManager(config, db)
    reader = UhfTcpReader({'id': 'real-frame-test', 'listenPort': 0})
    reader.credential_received.connect(lambda event: manager._receive(event, 3))
    manager.credential_received.connect(business.process_credential)
    logs = []; business.log_updated.connect(lambda *parts: logs.append(parts))
    assert reader.start()
    try:
        with socket.create_connection(('127.0.0.1', reader.server.serverPort())) as conn:
            frame = bytes.fromhex('09 00 EE 00 AE 1D AF 0B 4F 8F')
            conn.sendall(frame[:5]); pump(app)
            assert not logs
            conn.sendall(frame[5:] + frame); pump(app)
        assert pushed.wait(1)
        assert len(logs) == 1
        assert logs[0][3] == '一年级一班'
        assert logs[0][1] == '超高频标签 2921180939'
        business.tts_worker.add_text.assert_called_once()
        api.push_dismissal_notice.assert_called_once_with(
            'c1', '2921180939', dismissal_status=1, class_type=1, trigger_type=1)
        led.mark_dismissing.assert_called_once_with('c1', class_type=1)
    finally:
        reader.stop(); pump(app); business.cleanup()
