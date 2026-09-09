"""Synthetic active-mode EPC frames, not captured hardware data."""
import argparse
import socket
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.readers.uhf_protocol import encode_epc

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='模拟 UHF 标签上传；仅向明确指定的测试监听器发送')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=7000)
    p.add_argument('--epc', default='3005FB63AC1F3841EC880467')
    p.add_argument('--udp', action='store_true')
    p.add_argument('--count', type=int, default=1)
    p.add_argument('--interval', type=float, default=0.1)
    p.add_argument('--split', type=int, default=0)
    args = p.parse_args()
    frame = encode_epc(args.epc)
    print('模拟数据：', frame.hex(' ').upper())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if args.udp else socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect((args.host, args.port))
        for _ in range(args.count):
            if args.split and not args.udp:
                sock.sendall(frame[:args.split]); time.sleep(.05); sock.sendall(frame[args.split:])
            else:
                sock.sendall(frame)
            time.sleep(max(0, args.interval))
