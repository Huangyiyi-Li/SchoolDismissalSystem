from __future__ import annotations

import datetime
import logging
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket, QUdpSocket

from .system_status import AlertLevel, RuntimeStatusStore, ServiceState
from .udp_parser import (
    PACKET_HEADER,
    PACKET_LENGTH,
    extract_ascii_card_lines,
    extract_ascii_card_payloads,
    extract_tcp_packets,
    parse_udp_packet,
)

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
        self.tcp_client_ips: dict[int, str] = {}
        self.tcp_buffers: dict[int, bytearray] = {}
        self.tcp_packet_counts: dict[int, int] = {}
        self.tcp_connection_counts: dict[str, int] = {}
        self.tcp_connected_at: dict[int, float] = {}
        self.tcp_first_chunk_logged: set[int] = set()
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
        self.tcp_client_ips.clear()
        self.tcp_buffers.clear()
        self.tcp_connection_counts.clear()
        self.tcp_connected_at.clear()
        self.tcp_first_chunk_logged.clear()

    def process_pending_datagrams(self):
        while self.socket.hasPendingDatagrams():
            datagram, host, _port = self.socket.readDatagram(self.socket.pendingDatagramSize())
            ip = self._normalize_ip(host.toString())
            if len(datagram) == PACKET_LENGTH and datagram[:1] == bytes([PACKET_HEADER]):
                self.parse_packet(datagram, ip, protocol="udp")
                continue

            ascii_card_ids = extract_ascii_card_payloads(datagram)
            if ascii_card_ids:
                for card_id in ascii_card_ids:
                    self.parse_card_id(card_id, ip, protocol="udp-text")
                continue

            LOGGER.warning(
                "UDP parse error from %s: invalid packet length=%s hex=%s ascii=%s",
                ip,
                len(datagram),
                datagram[:32].hex(" "),
                "".join(chr(b) if 32 <= b <= 126 else "." for b in datagram[:32]),
            )
            self._set_status("udp", AlertLevel.WARNING, "udp parse warning", f"invalid packet length: {len(datagram)}")

    def _accept_tcp_connections(self):
        while self.tcp_server.hasPendingConnections():
            client = self.tcp_server.nextPendingConnection()
            client_id = id(client)
            peer_ip = self._normalize_ip(client.peerAddress().toString())
            stale_client_ids = [cid for cid, ip in self.tcp_client_ips.items() if ip == peer_ip]
            self.tcp_clients[client_id] = client
            self.tcp_client_ips[client_id] = peer_ip
            self.tcp_buffers[client_id] = bytearray()
            self.tcp_packet_counts[client_id] = 0
            self.tcp_connected_at[client_id] = time.perf_counter()
            try:
                client.setSocketOption(QAbstractSocket.SocketOption.KeepAliveOption, 1)
                client.setSocketOption(QAbstractSocket.SocketOption.LowDelayOption, 1)
            except Exception:
                LOGGER.debug("Failed to configure TCP reader socket options", exc_info=True)
            client.readyRead.connect(lambda cid=client_id: self._read_tcp_client(cid))
            client.disconnected.connect(lambda cid=client_id: self._handle_tcp_disconnect(cid))
            client.errorOccurred.connect(lambda _error, cid=client_id: self._handle_tcp_error(cid))
            self._mark_tcp_connected(peer_ip)
            if stale_client_ids:
                LOGGER.warning(
                    "Replacing %s stale TCP reader connection(s) from %s",
                    len(stale_client_ids),
                    peer_ip,
                )
                for stale_client_id in stale_client_ids:
                    self._close_tcp_client(
                        stale_client_id,
                        reason="superseded by newer connection",
                        emit_offline=False,
                    )
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

        if client_id not in self.tcp_first_chunk_logged:
            connected_at = self.tcp_connected_at.get(client_id)
            if connected_at is not None:
                LOGGER.info(
                    "TCP first payload latency ip=%s delay_ms=%.1f bytes=%s",
                    peer_ip,
                    (time.perf_counter() - connected_at) * 1000.0,
                    len(chunk),
                )
            self.tcp_first_chunk_logged.add(client_id)

        LOGGER.debug(
            "TCP reader chunk from %s: %s bytes hex=%s ascii=%s",
            peer_ip,
            len(chunk),
            chunk[:32].hex(" "),
            "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk[:32]),
        )

        buffer = self.tcp_buffers.setdefault(client_id, bytearray())
        buffer.extend(chunk)
        packets, pending = extract_tcp_packets(buffer)
        card_lines, pending = extract_ascii_card_lines(pending)
        self.tcp_buffers[client_id] = pending

        if not packets and not card_lines:
            LOGGER.debug(
                "TCP reader chunk from %s did not form a complete packet yet; buffered=%s bytes",
                peer_ip,
                len(pending),
            )

        for packet in packets:
            self.tcp_packet_counts[client_id] = self.tcp_packet_counts.get(client_id, 0) + 1
            self.parse_packet(packet, peer_ip, protocol="tcp")

        for card_id in card_lines:
            self.tcp_packet_counts[client_id] = self.tcp_packet_counts.get(client_id, 0) + 1
            self.parse_card_id(card_id, peer_ip, protocol="tcp-text")

    def _handle_tcp_disconnect(self, client_id: int):
        self._close_tcp_client(client_id, reason="disconnected")

    def _handle_tcp_error(self, client_id: int):
        client = self.tcp_clients.get(client_id)
        if client is None:
            return

        peer_ip = self.tcp_client_ips.get(client_id) or self._normalize_ip(client.peerAddress().toString())
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

    def _mark_tcp_connected(self, ip):
        self.tcp_connection_counts[ip] = self.tcp_connection_counts.get(ip, 0) + 1
        self._mark_device_online(ip)

    def _mark_tcp_disconnected(self, ip):
        remaining = self.tcp_connection_counts.get(ip, 0)
        if remaining > 1:
            self.tcp_connection_counts[ip] = remaining - 1
            return
        self.tcp_connection_counts.pop(ip, None)
        self.devices.pop(ip, None)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        device_name = self.db.get_device_name(ip) if self.db else ip
        self.device_updated.emit(ip, now, "离线", device_name)

    def count_online_devices(self, now=None):
        now = now or datetime.datetime.now()
        online_ips = set(self.tcp_connection_counts.keys())
        online_ips.update(
            ip
            for ip, last_seen in self.devices.items()
            if ip not in self.tcp_connection_counts
            and isinstance(last_seen, datetime.datetime)
            and (now - last_seen).total_seconds() <= 60
        )
        return len(online_ips)

    def parse_packet(self, data, ip, protocol="udp"):
        started = time.perf_counter()
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
        emit_started = time.perf_counter()
        self.card_swiped.emit(card_id_str, ip)
        LOGGER.info(
            "Reader packet processed protocol=%s ip=%s card_id=%s parse_ms=%.1f emit_ms=%.1f total_ms=%.1f",
            protocol,
            ip,
            card_id_str,
            (emit_started - started) * 1000.0,
            (time.perf_counter() - emit_started) * 1000.0,
            (time.perf_counter() - started) * 1000.0,
        )

    def parse_card_id(self, card_id, ip, protocol="tcp-text"):
        started = time.perf_counter()
        self._mark_device_online(ip)
        normalized_card_id = str(card_id).strip()
        if not normalized_card_id or not normalized_card_id.isdigit():
            LOGGER.warning("Discarded non-numeric card id from %s via %s: %r", ip, protocol, card_id)
            self._set_status(protocol, AlertLevel.WARNING, f"{protocol} invalid card", str(card_id))
            return

        print(f"[{protocol.upper()}] Received Card ID: {normalized_card_id} from {ip}")
        self._set_status(protocol, AlertLevel.OK, f"{protocol} card parsed", normalized_card_id)
        emit_started = time.perf_counter()
        self.card_swiped.emit(normalized_card_id, ip)
        LOGGER.info(
            "Reader card processed protocol=%s ip=%s card_id=%s normalize_ms=%.1f emit_ms=%.1f total_ms=%.1f",
            protocol,
            ip,
            normalized_card_id,
            (emit_started - started) * 1000.0,
            (time.perf_counter() - emit_started) * 1000.0,
            (time.perf_counter() - started) * 1000.0,
        )

    def check_offline_devices(self):
        now = datetime.datetime.now()
        for ip, last_seen in list(self.devices.items()):
            if ip in self.tcp_connection_counts:
                continue
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

    def _close_tcp_client(self, client_id: int, *, reason: str, emit_offline: bool = True):
        client = self.tcp_clients.pop(client_id, None)
        pending = self.tcp_buffers.pop(client_id, bytearray())
        packet_count = self.tcp_packet_counts.pop(client_id, 0)
        self.tcp_connected_at.pop(client_id, None)
        self.tcp_first_chunk_logged.discard(client_id)
        peer_ip = self.tcp_client_ips.pop(client_id, None)
        if client is None and peer_ip is None:
            return

        if peer_ip is None and client is not None:
            peer_ip = self._normalize_ip(client.peerAddress().toString())

        if pending and peer_ip:
            LOGGER.warning(
                "TCP reader %s from %s with %s buffered bytes left hex=%s",
                reason,
                peer_ip,
                len(pending),
                bytes(pending[:32]).hex(" "),
            )

        if peer_ip and emit_offline:
            self._mark_tcp_disconnected(peer_ip)
        elif peer_ip:
            remaining = self.tcp_connection_counts.get(peer_ip, 0)
            if remaining > 1:
                self.tcp_connection_counts[peer_ip] = remaining - 1
            else:
                self.tcp_connection_counts.pop(peer_ip, None)

        if client is not None:
            try:
                client.abort()
            except Exception:
                LOGGER.debug("Failed to abort TCP reader socket cleanly", exc_info=True)
            client.deleteLater()

        LOGGER.info("TCP reader %s from %s packets=%s", reason, peer_ip or "unknown", packet_count)
