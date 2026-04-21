from PyQt6.QtNetwork import QUdpSocket, QHostAddress
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import datetime

from .system_status import AlertLevel, RuntimeStatusStore, ServiceState
from .udp_parser import parse_udp_packet

class UDPServerService(QObject):
    # Signal to emit when a valid card is swiped: (card_id, ip_address)
    card_swiped = pyqtSignal(str, str)
    # Signal to update device list in UI: (ip, last_seen, status, name) - Updated signature
    device_updated = pyqtSignal(str, str, str, str) 

    def __init__(self, port=39169, db_manager=None, status_store=None):
        super().__init__()
        self.port = port
        self.db = db_manager
        self.status_store = status_store or RuntimeStatusStore()
        self.socket = None
        self.devices = {}  # {ip: last_seen_datetime}
        self.packet_history = {}

    def _set_status(self, level, summary, detail=""):
        now = datetime.datetime.now()
        self.status_store.update(
            "udp",
            ServiceState(
                name="udp",
                level=level,
                summary=summary,
                detail=detail,
                updated_at=now,
            ),
        )
        
    def start(self):
        self.socket = QUdpSocket(self)
        if self.socket.bind(QHostAddress.SpecialAddress.Any, self.port):
            self.socket.readyRead.connect(self.process_pending_datagrams)
            print(f"[UDP] Listening on port {self.port}")
            self._set_status(AlertLevel.OK, "udp listening", f"port={self.port}")
            return True
        else:
            print(f"[UDP] Failed to bind port {self.port}")
            self._set_status(AlertLevel.CRITICAL, "udp bind failed", f"port={self.port}")
            return False

    def stop(self):
        if self.socket:
            self.socket.close()

    def process_pending_datagrams(self):
        while self.socket.hasPendingDatagrams():
            datagram, host, port = self.socket.readDatagram(self.socket.pendingDatagramSize())
            ip = host.toString()
            # Handle IPv6 mapped IPv4
            if ip.startswith("::ffff:"):
                ip = ip[7:]
                
            self.parse_datagram(datagram, ip)

    def parse_datagram(self, data, ip):
        # Update device status
        now = datetime.datetime.now()
        self.devices[ip] = now
        time_str = now.strftime("%H:%M:%S")
        
        device_name = ip
        if self.db:
            try:
                # Persist and get name
                # Only update DB if needed (optimization: verify frequency?)
                # For now, upsert every packet might be heavy if high traffic.
                # But traffic is low (card swipes).
                self.db.upsert_device(ip, last_seen=now)
                device_name = self.db.get_device_name(ip) or ip
            except Exception as e:
                print(f"[UDP] Device DB Error ({ip}): {e}")
                device_name = ip

        self.device_updated.emit(ip, time_str, "在线", device_name)

        # Protocol Parsing + Deduplication
        try:
            parsed = parse_udp_packet(data)
        except ValueError as e:
            print(f"[UDP] Parse Error from {ip}: {e}")
            self._set_status(AlertLevel.WARNING, "udp parse warning", str(e))
            return

        seq_id = parsed.sequence_id

        try:
            # Key for deduplication: (IP, Sequence)
            dedup_key = (ip, seq_id)
            packet_time = datetime.datetime.now()

            # Cleanup old history (older than 10 seconds)
            cutoff = packet_time - datetime.timedelta(seconds=10)
            to_remove = [k for k, t in self.packet_history.items() if t < cutoff]
            for k in to_remove:
                del self.packet_history[k]

            if dedup_key in self.packet_history:
                print(f"[UDP] Dropping duplicate packet from {ip} (Seq: {seq_id})")
                return

            self.packet_history[dedup_key] = packet_time
        except Exception as e:
            print(f"[UDP] Dedup Error: {e}")

        card_id_str = parsed.card_id
        print(f"[UDP] Received Card ID: {card_id_str} from {ip} Seq:{seq_id}")
        self._set_status(AlertLevel.OK, "udp packet parsed", f"seq={seq_id}")
        self.card_swiped.emit(card_id_str, ip)

    def check_offline_devices(self):
        now = datetime.datetime.now()
        for ip, last_seen in list(self.devices.items()):
            delta = (now - last_seen).total_seconds()
            
            device_name = ip
            if self.db:
                device_name = self.db.get_device_name(ip)

            if delta > 300: # 5 minutes clear
                del self.devices[ip]
                # self.device_updated.emit(ip, "N/A", "移除", device_name) 
            elif delta > 60: # 1 minute offline
                time_str = last_seen.strftime("%H:%M:%S")
                self.device_updated.emit(ip, time_str, "离线", device_name)
