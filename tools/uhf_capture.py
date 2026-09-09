"""Raw TCP/UDP capture. Run separately from the app, on a different/free port."""
import argparse
import socketserver
from datetime import datetime


def report(peer, data):
    print(f'{datetime.now().isoformat()} {peer} {data.hex(" ").upper()}', flush=True)


class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        print(f'已连接 {self.client_address}', flush=True)
        while data := self.request.recv(65536):
            report(self.client_address, data)


class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        report(self.client_address, self.request[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='UHF 原始数据抓包，不触发放学')
    parser.add_argument('--port', type=int, default=7001)
    parser.add_argument('--udp', action='store_true')
    args = parser.parse_args()
    cls = socketserver.ThreadingUDPServer if args.udp else socketserver.ThreadingTCPServer
    cls.daemon_threads = True
    with cls(('0.0.0.0', args.port), UDP if args.udp else TCP) as server:
        print(f'监听 {args.port}，Ctrl+C 结束', flush=True)
        server.serve_forever()
