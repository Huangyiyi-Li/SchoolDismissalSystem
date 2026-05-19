from PyQt6.QtNetwork import QUdpSocket, QHostAddress
from PyQt6.QtCore import QObject, pyqtSignal
import datetime

class UDPServerService(QObject):
    # Signal to emit when a valid card is swiped: (card_id, ip_address)
    card_swiped = pyqtSignal(str, str)

    def __init__(self, port=39169, db_manager=None):
        super().__init__()
        self.port = port
        self.db = db_manager
        self.socket = None
        
    def start(self):
        self.socket = QUdpSocket(self)
        if self.socket.bind(QHostAddress.SpecialAddress.Any, self.port):
            self.socket.readyRead.connect(self.process_pending_datagrams)
            print(f"[UDP] Listening on port {self.port}")
            return True
        else:
            print(f"[UDP] Failed to bind port {self.port}")
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
        # Protocol Parsing
        # Fixed length 22 bytes
        if len(data) == 22:
            # Protocol check (Header 0xC1)
            # User format: [Magic 3] ... [Seq 1 at idx 7]
            if data[0] == 0xC1:
                # Deduplication based on Sequence Number (Byte 7)
                try:
                    seq_id = data[7]
                    
                    # Key for deduplication: (IP, Sequence)
                    dedup_key = (ip, seq_id)
                    packet_time = datetime.datetime.now()
                    
                    # Cleanup old history (older than 10 seconds)
                    cutoff = packet_time - datetime.timedelta(seconds=10)
                    # Create a list to modify dictionary during iteration (Python 3)
                    to_remove = [k for k, t in getattr(self, 'packet_history', {}).items() if t < cutoff]
                    
                    if not hasattr(self, 'packet_history'):
                        self.packet_history = {}
                        
                    for k in to_remove:
                        del self.packet_history[k]
                    
                    # Check if exists
                    if dedup_key in self.packet_history:
                        # Already processed this sequence from this IP
                        print(f"[UDP] Dropping duplicate packet from {ip} (Seq: {seq_id})")
                        return # Skip processing
                        
                    # Add to history
                    self.packet_history[dedup_key] = packet_time
                    
                except Exception as e:
                    print(f"[UDP] Dedup Error: {e}")

                # Correct Analysis:
                # Bytes 10-13 is Card ID (Little Endian)
                # Example: C1 16 F4 D9 -> 0xD9F416C1 -> 3656652481
                card_bytes = data[10:14]
                try:
                    # Convert bytes to integer (little endian)
                    card_int = int.from_bytes(card_bytes, byteorder='little')
                    card_id_str = str(card_int)
                    
                    print(f"[UDP] Received Card ID: {card_id_str} (Hex: {card_bytes.hex().upper()}) from {ip} Seq:{seq_id}")
                    self.card_swiped.emit(card_id_str, ip)
                except Exception as e:
                    print(f"[UDP] Error parsing card bytes: {e}")
            else:
                print(f"[UDP] Invalid Header {data[0]:02X} from {ip}")
        else:
            print(f"[UDP] Invalid Length {len(data)} from {ip}")
