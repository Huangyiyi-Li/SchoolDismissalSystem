import socket
import datetime

def main():
    UDP_IP = "0.0.0.0"
    UDP_PORT = 39169

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((UDP_IP, UDP_PORT))
        print(f"[{datetime.datetime.now()}] 正在监听 UDP 端口 {UDP_PORT} ...")
        print("请在刷卡器上刷卡，程序将打印接收到的数据和设备IP。")
        print("按 Ctrl+C 停止。")
    except OSError as e:
        print(f"端口绑定失败: {e}")
        print("请检查端口 39169 是否被其他程序占用。")
        return

    try:
        while True:
            data, addr = sock.recvfrom(4096)  # Buffer size
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")
            
            print("-" * 50)
            print(f"时间: {timestamp}")
            print(f"来自设备 IP: {addr[0]}  端口: {addr[1]}")
            print(f"数据长度: {len(data)} bytes")
            print(f"HEX (十六进制): {data.hex(' ').upper()}")
            try:
                print(f"STR (字符串): {data.decode('utf-8', errors='ignore')}")
            except:
                pass
            print("-" * 50)
    except KeyboardInterrupt:
        print("\n已停止监听。")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
