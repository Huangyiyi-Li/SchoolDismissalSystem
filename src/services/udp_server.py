from __future__ import annotations

import datetime
import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket, QUdpSocket

from .system_status import AlertLevel, RuntimeStatusStore, ServiceState
from .udp_parser import extract_tcp_packets, parse_udp_packet

LOGGER = logging.getLogger(__name__)


class UDPServerService(QObject):
    # Signal to emit when a valid card is swiped: (card_id, ip_address)
    card_swiped = pyqtSignal(str, str)
    # Signal to update device list in UI: (ip, last_seen, status, name)
    device_updated = pyqtSignal(str, str, str, str)

    def __init__(self, port=39169, db_manager=None, status_store=None):
        super().__init__()
        self.port = port
        self.db = db_manager
        self.status_store = status_store or RuntimeStatusStore()
        self.socket = None
        self.tcp_server = None
        self.tcp_clients: dict[int, QTcpSocket] = {}
        self.tcp_buffers: dict[int, bytearray] = {}
        self.tcp_packet_counts: dict[int, int] = {}
        self.devices = {}  # {ip: last_seen_datetime}
        self.packet_history = {}

    def _set_status(self, service_name, level, summary, detail=""):
        now = datetime.datetime.now()
        self.status_store.update(
            service_name,
            ServiceState(
                name=service_name,
                level=level,
                summary=summary,
                detail=detail,
                updated_at=now,
            ),
        )

    def start(self):
        udp_ok = self._start_udp()
        tcp_ok = self._start_tcp()
        return udp_ok and tcp_ok

    def _start_udp(self):
        self.socket = QUdpSocket(self)
        if self.socket.bind(QHostAddress.SpecialAddress.Any, self.port):
            self.socket.readyRead.connect(self.process_pending_datagrams)
            print(f"[UDP] Listening on port {self.port}")
            self._set_status("udp", AlertLevel.OK, "udp listening", f"port={self.port}")
            return True

        print(f"[UDP] Failed to bind port {self.port}")
        self._set_status("udp", AlertLevel.CRITICAL, "udp bind failed", f"port={self.port}")
        return False

    def _start_tcp(self):
        self.tcp_server = QTcpServer(self)
        if self.tcp_server.listen(QHostAddress.SpecialAddress.Any, self.port):
            self.tcp_server.newConnection.connect(self._accept_tcp_connections)
            print(f"[TCP] Listening on port {self.port}")
            self._set_status("tcp", AlertLevel.OK, "tcp listening", f"port={self.port}")
            return True

        print(f"[TCP] Failed to listen on port {self.port}")
        self._set_status("tcp", AlertLevel.CRITICAL, "tcp bind failed", f"port={self.port}")
        return False

    def stop(self):
        if self.socket:
            self.socket.close()

        if self.tcp_server:
            self.tcp_server.close()

        for socket_obj in list(self.tcp_clients.values()):
            socket_obj.abort()
            socket_obj.deleteLater()

        self.tcp_clients.clear()
        self.tcp_buffers.clear()

    def process_pending_datagrams(self):
        while self.socket.hasPendingDatagrams():
            datagram, host, _port = self.socket.readDatagram(self.socket.pendingDatagramSize())
            ip = self._normalize_ip(host.toString())
            self.parse_packet(datagram, ip, protocol="udp")

    def _accept_tcp_connections(self):
        while self.tcp_server.hasPendingConnections():
            client = self.tcp_server.nextPendingConnection()
            client_id = id(client)
            self.tcp_clients[client_id] = client
            self.tcp_buffers[client_id] = bytearray()
            self.tcp_packet_counts[client_id] = 0
            client.readyRead.connect(lambda cid=client_id: self._read_tcp_client(cid))
            client.disconnected.connect(lambda cid=client_id: self._handle_tcp_disconnect(cid))
            client.errorOccurred.connect(lambda _error, cid=client_id: self._handle_tcp_error(cid))
            peer_ip = self._normalize_ip(client.peerAddress().toString())
            LOGGER.info("Accepted TCP reader connection from %s", peer_ip)

    def _read_tcp_client(self, client_id: int):
        client = self.tcp_clients.get(client_id)
        if client is None:
            return

        peer_ip = self._normalize_ip(client.peerAddress().toString())
        self._mark_device_online(peer_ip)

        chunk = bytes(client.readAll())
        if not chunk:
            return

        LOGGER.info(
            "TCP reader chunk from %s: %s bytes hex=%s ascii=%s",
            peer_ip,
            len(chunk),
            chunk[:32].hex(" "),
            "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk[:32]),
        )

        buffer = self.tcp_buffers.setdefault(client_id, bytearray())
        buffer.extend(chunk)
        packets, pending = extract_tcp_packets(buffer)
        self.tcp_buffers[client_id] = pending

        if not packets:
            LOGGER.info(
                "TCP reader chunk from %s did not form a complete packet yet; buffered=%s bytes",
                peer_ip,
                len(pending),
            )

        for packet in packets:
            self.tcp_packet_counts[client_id] = self.tcp_packet_counts.get(client_id, 0) + 1
            self.parse_packet(packet, peer_ip, protocol="tcp")

    def _handle_tcp_disconnect(self, client_id: int):
        client = self.tcp_clients.pop(client_id, None)
        pending = self.tcp_buffers.pop(client_id, bytearray())
        packet_count = self.tcp_packet_counts.pop(client_id, 0)
        if client is None:
            return

        peer_ip = self._normalize_ip(client.peerAddress().toString())
        if pending:
            LOGGER.warning(
                "TCP reader disconnected from %s with %s buffered bytes left hex=%s",
                peer_ip,
                len(pending),
                bytes(pending[:32]).hex(" "),
            )
        LOGGER.info("TCP reader disconnected from %s packets=%s", peer_ip, packet_count)
        client.deleteLater()

    def _handle_tcp_error(self, client_id: int):
        client = self.tcp_clients.get(client_id)
        if client is None:
            return

        peer_ip = self._normalize_ip(client.peerAddress().toString())
        error_text = client.errorString()
        LOGGER.warning("TCP reader error from %s: %s", peer_ip, error_text)
        self._set_status("tcp", AlertLevel.WARNING, "tcp client warning", error_text)

    def _normalize_ip(self, ip):
        if ip.startswith("::ffff:"):
            return ip[7:]
        return ip

    def _device_name_for_ip(self, ip):
        device_name = ip
        if self.db:
            try:
                self.db.upsert_device(ip, last_seen=datetime.datetime.now())
                device_name = self.db.get_device_name(ip) or ip
            except Exception as exc:
                print(f"[Device] Device DB Error ({ip}): {exc}")
                device_name = ip
        return device_name

    def _mark_device_online(self, ip):
        now = datetime.datetime.now()
        self.devices[ip] = now
        time_str = now.strftime("%H:%M:%S")
        device_name = self._device_name_for_ip(ip)
        self.device_updated.emit(ip, time_str, "在线", device_name)

    def parse_packet(self, data, ip, protocol="udp"):
        self._mark_device_online(ip)

        try:
            parsed = parse_udp_packet(data)
        except ValueError as exc:
            print(f"[{protocol.upper()}] Parse Error from {ip}: {exc}")
            self._set_status(protocol, AlertLevel.WARNING, f"{protocol} parse warning", str(exc))
            return

        seq_id = parsed.sequence_id

        try:
            dedup_key = (ip, protocol, seq_id)
            packet_time = datetime.datetime.now()

            cutoff = packet_time - datetime.timedelta(seconds=10)
            to_remove = [k for k, t in self.packet_history.items() if t < cutoff]
            for key in to_remove:
                del self.packet_history[key]

            if dedup_key in self.packet_history:
                print(f"[{protocol.upper()}] Dropping duplicate packet from {ip} (Seq: {seq_id})")
                return

            self.packet_history[dedup_key] = packet_time
        except Exception as exc:
            print(f"[{protocol.upper()}] Dedup Error: {exc}")

        card_id_str = parsed.card_id
        print(f"[{protocol.upper()}] Received Card ID: {card_id_str} from {ip} Seq:{seq_id}")
        self._set_status(protocol, AlertLevel.OK, f"{protocol} packet parsed", f"seq={seq_id}")
        self.card_swiped.emit(card_id_str, ip)

    def check_offline_devices(self):
        now = datetime.datetime.now()
        for ip, last_seen in list(self.devices.items()):
            delta = (now - last_seen).total_seconds()

            device_name = ip
            if self.db:
                device_name = self.db.get_device_name(ip)

            if delta > 300:
                del self.devices[ip]
            elif delta > 60:
                time_str = last_seen.strftime("%H:%M:%S")
                self.device_updated.emit(ip, time_str, "离线", device_name)

        if self.tcp_server is not None and self.tcp_server.isListening():
            self._set_status("tcp", AlertLevel.OK, "tcp listening", f"port={self.port}")
        elif self.tcp_server is not None:
            self._set_status("tcp", AlertLevel.WARNING, "tcp stopped", f"port={self.port}")
