"""Run the Mac test platform and one temporary HTTPS tunnel together."""

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]{20,}\.trycloudflare\.com")


def cloudflared_path():
    homebrew = Path("/opt/homebrew/opt/cloudflared/bin/cloudflared")
    return str(homebrew) if homebrew.is_file() else shutil.which("cloudflared")


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    tunnel = None
    server = None
    try:
        public_url = None
        recent = deque(maxlen=6)
        for attempt in range(3):
            tunnel = subprocess.Popen(
                [cloudflared_path(), "tunnel", "--url", "http://127.0.0.1:8765", "--no-autoupdate"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                bufsize=1)
            lines = queue.Queue()

            def read_tunnel(process, output_queue):
                for line in process.stdout:
                    output_queue.put(line)

            threading.Thread(target=read_tunnel, args=(tunnel, lines), daemon=True).start()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and tunnel.poll() is None:
                try:
                    line = lines.get(timeout=1)
                except queue.Empty:
                    continue
                recent.append(line.strip())
                match = TUNNEL_PATTERN.search(line)
                if match:
                    public_url = match.group(0)
                    break
            if public_url:
                break
            stop(tunnel)
            tunnel = None
            if attempt < 2:
                print("隧道暂未建立，正在重试…", flush=True)
                time.sleep(2)
        if not public_url:
            raise RuntimeError("临时 HTTPS 隧道未取得地址：" + " | ".join(recent))

        env = dict(os.environ)
        env["ANDROID_MOCK_PUBLIC_URL"] = public_url
        env.setdefault("ANDROID_HOME", str(Path.home() / "Andriod"))
        env.setdefault("JAVA_HOME", "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
        server = subprocess.Popen([sys.executable, str(ROOT / "tools/android_mock_platform.py")],
                                  cwd=ROOT, env=env)
        (ROOT / ".local").mkdir(exist_ok=True)
        (ROOT / ".local/current_public_url").write_text(public_url, encoding="utf-8")
        print("Mac 管理页：http://127.0.0.1:8766/admin", flush=True)
        print("话机入口：" + public_url, flush=True)
        print("关闭本进程时，平台和临时隧道会一起停止。", flush=True)
        while tunnel.poll() is None and server.poll() is None:
            time.sleep(1)
        raise RuntimeError("测试平台或隧道已退出，请重新启动")
    except KeyboardInterrupt:
        print("正在停止测试平台…", flush=True)
    finally:
        stop(server)
        stop(tunnel)


if __name__ == "__main__":
    main()
