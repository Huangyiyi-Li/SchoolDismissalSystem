"""Persist one-device test commands, bounded diagnostics, and immutable APK releases."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path


COMMANDS = {"led_ping", "led_send_page"}
EVENT_TYPES = COMMANDS | {"heartbeat", "update"}
MAX_APK_BYTES = 40 * 1024 * 1024
MAX_EVENTS = 100
COMMAND_TTL_SECONDS = 300
PACKAGE_NAME = "cn.xxt.dismissal.poc"


def now_text():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def sdk_tool(name):
    homes = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             str(Path.home() / "Andriod"), str(Path.home() / "Library/Android/sdk")]
    for home in filter(None, homes):
        build_tools = Path(home) / "build-tools"
        if build_tools.is_dir():
            for version in sorted(build_tools.iterdir(), reverse=True):
                candidate = version / name
                if candidate.is_file():
                    return str(candidate)
    raise ValueError(f"找不到 Android SDK 工具 {name}，请设置 ANDROID_HOME")


def inspect_apk(path):
    env = dict(os.environ)
    env.setdefault("JAVA_HOME", "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
    try:
        badging = subprocess.run([sdk_tool("aapt"), "dump", "badging", str(path)],
                                 capture_output=True, text=True, check=True, timeout=20, env=env).stdout
        certificates = subprocess.run([sdk_tool("apksigner"), "verify", "--print-certs", str(path)],
                                      capture_output=True, text=True, check=True, timeout=20, env=env).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        raise ValueError("APK 无法通过 Android 包检查或签名验证") from error
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",
                        badging, re.MULTILINE)
    signer = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})", certificates)
    if not package or not signer:
        raise ValueError("APK 缺少包名、版本或签名信息")
    return {"packageName": package.group(1), "versionCode": int(package.group(2)),
            "versionName": package.group(3), "signerSha256": signer.group(1)}


class RemoteControlStore:
    def __init__(self, root, inspector=inspect_apk, clock=time.time):
        self.root = Path(root)
        self.inspector = inspector
        self.clock = clock
        self.lock = threading.Lock()
        self.commands_file = self.root / "android_commands.json"
        self.events_file = self.root / "android_events.json"
        self.release_file = self.root / "android_release.json"
        self.signer_file = self.root / "android_signer_sha256"
        self.releases_dir = self.root / "releases"

    def command_state(self):
        command = read_json(self.commands_file, None)
        if command and command["status"] == "queued" and command["expiresAt"] < self.clock():
            command["status"] = "expired"
            write_json(self.commands_file, command)
        return command

    def snapshot(self):
        with self.lock:
            command = self.command_state()
            return {"command": command if command and command["status"] == "queued" else None,
                    "release": read_json(self.release_file, None)}

    def admin_state(self):
        with self.lock:
            return {"command": self.command_state(),
                    "release": read_json(self.release_file, None),
                    "events": read_json(self.events_file, [])[-MAX_EVENTS:][::-1]}

    def enqueue(self, command_type):
        if command_type not in COMMANDS:
            raise ValueError("不支持的远程测试命令")
        with self.lock:
            current = self.command_state()
            if current and current["status"] == "queued":
                raise ValueError("上一条远程测试仍在等待话机执行或回传")
            command = {"id": uuid.uuid4().hex, "type": command_type,
                       "status": "queued", "createdAt": now_text(),
                       "expiresAt": int(self.clock()) + COMMAND_TTL_SECONDS}
            write_json(self.commands_file, command)
            return command

    def record_event(self, event):
        if not isinstance(event, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(event.get("eventId", ""))):
            raise ValueError("事件 ID 无效")
        if event.get("type") not in EVENT_TYPES or not isinstance(event.get("success"), bool):
            raise ValueError("事件类型或结果无效")
        if not isinstance(event.get("versionCode"), int) or event["versionCode"] < 1:
            raise ValueError("应用版本号无效")
        if not isinstance(event.get("configVersion"), int) or event["configVersion"] < 0:
            raise ValueError("配置版本号无效")
        for key in ("message", "appVersion", "controller"):
            if not isinstance(event.get(key), str) or len(event[key]) > 500:
                raise ValueError(f"事件字段 {key} 无效")
        command_id = event.get("commandId")
        if command_id is not None and not re.fullmatch(r"[0-9a-f]{32}", str(command_id)):
            raise ValueError("命令 ID 无效")
        sanitized = {key: event[key] for key in
                     ("eventId", "type", "success", "versionCode", "configVersion",
                      "message", "appVersion", "controller")}
        sanitized["commandId"] = command_id
        sanitized["receivedAt"] = now_text()
        with self.lock:
            events = read_json(self.events_file, [])
            if any(item["eventId"] == sanitized["eventId"] for item in events):
                return False
            write_json(self.events_file, (events + [sanitized])[-MAX_EVENTS:])
            command = self.command_state()
            if command and command["status"] == "queued" and command["id"] == command_id \
                    and command["type"] == sanitized["type"]:
                command["status"] = "completed"
                command["result"] = {"success": sanitized["success"],
                                     "message": sanitized["message"],
                                     "receivedAt": sanitized["receivedAt"]}
                write_json(self.commands_file, command)
            return True

    def publish(self, source):
        source = Path(source)
        size = source.stat().st_size
        if not 1 <= size <= MAX_APK_BYTES:
            raise ValueError("APK 大小无效或超过 40 MB")
        metadata = self.inspector(source)
        if metadata["packageName"] != PACKAGE_NAME:
            raise ValueError("APK 包名与话机联调应用不一致")
        if not self.signer_file.exists():
            raise ValueError("缺少已安装版本的签名指纹，不能发布升级包")
        if metadata["signerSha256"] != self.signer_file.read_text(encoding="utf-8").strip():
            raise ValueError("APK 签名与话机已安装版本不一致")
        digest = hashlib.sha256()
        with source.open("rb") as input_file:
            for chunk in iter(lambda: input_file.read(65536), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        with self.lock:
            current = read_json(self.release_file, None)
            if current and metadata["versionCode"] <= current["versionCode"]:
                raise ValueError("新 APK 版本号必须高于当前发布版本")
            self.releases_dir.mkdir(parents=True, exist_ok=True)
            target = self.releases_dir / f"{sha256}.apk"
            if not target.exists():
                shutil.copyfile(source, target)
            release = {"packageName": PACKAGE_NAME, "versionCode": metadata["versionCode"],
                       "versionName": metadata["versionName"], "sha256": sha256,
                       "size": size, "downloadPath": f"/api/releases/{sha256}.apk",
                       "publishedAt": now_text()}
            write_json(self.release_file, release)
            return release
