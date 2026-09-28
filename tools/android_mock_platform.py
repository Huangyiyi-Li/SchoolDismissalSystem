"""Mac-only test platform for Android dismissal settings missing from the live API.

Class/card data and school schedules remain on the existing rest.xxt.cn APIs.
Run: python3 tools/android_mock_platform.py
Open http://127.0.0.1:8766/admin on the Mac to edit the test settings.
"""

import argparse
import html
import json
import os
import secrets
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse

from android_remote_control import MAX_APK_BYTES, RemoteControlStore


STATE_FILE = Path(__file__).resolve().parent.parent / ".local" / "android_mock_config.json"
DIAGNOSTIC_FILE = STATE_FILE.with_name("android_led_diagnostic.json")
TOKEN_FILE = STATE_FILE.with_name("android_device_report_token")
APK_TOKEN_FILE = STATE_FILE.with_name("android_apk_download_token")
PAIR_TOKEN_FILE = STATE_FILE.with_name("android_pair_token")
APK_FILE = Path(__file__).resolve().parent.parent / "android-poc/app/build/outputs/apk/debug/app-debug.apk"
PUBLIC_URL = os.environ.get("ANDROID_MOCK_PUBLIC_URL", "").rstrip("/")
CONFIG_LOCK = threading.Lock()
REMOTE = RemoteControlStore(STATE_FILE.parent)


def ensure_tokens():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    for path, bytes_count in ((TOKEN_FILE, 24), (APK_TOKEN_FILE, 16), (PAIR_TOKEN_FILE, 16)):
        if not path.exists():
            path.write_text(secrets.token_hex(bytes_count), encoding="utf-8")
        path.chmod(0o600)


def pair_url():
    return PUBLIC_URL + "/pair/" + PAIR_TOKEN_FILE.read_text(encoding="utf-8").strip() if PUBLIC_URL else ""


def pair_html():
    deep_link = "xxtdismissal://connect?" + urlencode({"url": PUBLIC_URL, "token": report_token()})
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>连接放学联调平台</title><body style='font:20px sans-serif;padding:30px'>"
            "<h1>连接放学联调平台</h1><p>请在已安装联调版的话机上点下面的按钮。</p>"
            f"<p><a href='{html.escape(deep_link, quote=True)}'>连接话机应用</a></p>"
            "<p>连接后返回放学模块，等待状态更新。</p></body></html>")


def qr_png(value):
    result = subprocess.run(["/usr/bin/swift", str(Path(__file__).with_name("create_qr.swift"))],
                            input=value.encode("utf-8"), capture_output=True, timeout=30)
    if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG"):
        raise RuntimeError("无法生成配对二维码")
    return result.stdout


def download_url():
    if not PUBLIC_URL:
        return ""
    release = REMOTE.snapshot()["release"]
    if release:
        return PUBLIC_URL + release["downloadPath"] + "?download=" + download_token()
    return PUBLIC_URL + "/api/debug-apk/" + download_token() if APK_FILE.is_file() else ""
DEFAULT = {
    "version": 1,
    "schoolId": "40125",
    "dismissalEnabled": True,
    "testMode": True,
    "voice": {
        "speed": 1.0,
        "volumePercent": 80,
        "repeatCount": 2,
        "repeatIntervalSeconds": 1,
    },
    "led": {
        "enabled": False,
        "controllerIp": "",
        "controllerPort": 5005,
        "width": 1024,
        "height": 96,
        "schoolTitle": "放学信息",
        "gradesPerPage": 2,
        "pageSeconds": 8,
        "textSize": 20,
    },
}


def read_config():
    if STATE_FILE.exists():
        return validate(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return json.loads(json.dumps(DEFAULT, ensure_ascii=False))


def validate(value):
    if not isinstance(value, dict):
        raise ValueError("配置必须是 JSON 对象")
    result = json.loads(json.dumps(DEFAULT, ensure_ascii=False))
    school = str(value.get("schoolId", result["schoolId"])).strip()
    if not school.isdigit():
        raise ValueError("学校编号只能是数字")
    result["schoolId"] = school
    for key in ("dismissalEnabled", "testMode"):
        incoming = value.get(key, result[key])
        if not isinstance(incoming, bool):
            raise ValueError(f"{key} 必须是布尔值")
        result[key] = incoming
    voice = value.get("voice", {})
    led = value.get("led", {})
    if not isinstance(voice, dict) or not isinstance(led, dict):
        raise ValueError("voice 和 led 必须是对象")
    v = result["voice"]
    for key, low, high, cast in (
        ("speed", 0.5, 2.0, float),
        ("volumePercent", 0, 100, int),
        ("repeatCount", 1, 10, int),
        ("repeatIntervalSeconds", 0, 30, int),
    ):
        v[key] = cast(voice.get(key, v[key]))
        if not low <= v[key] <= high:
            raise ValueError(f"voice.{key} 超出范围")
    d = result["led"]
    enabled = led.get("enabled", d["enabled"])
    if not isinstance(enabled, bool):
        raise ValueError("led.enabled 必须是布尔值")
    d["enabled"] = enabled
    d["controllerIp"] = str(led.get("controllerIp", d["controllerIp"])).strip()
    d["schoolTitle"] = str(led.get("schoolTitle", d["schoolTitle"])).strip()
    if not 1 <= len(d["schoolTitle"]) <= 20:
        raise ValueError("LED 标题需为 1–20 字")
    if enabled and not d["controllerIp"]:
        raise ValueError("启用 LED 时必须填写控制卡 IP")
    for key, low, high in (
        ("controllerPort", 1, 65535), ("width", 64, 2048),
        ("height", 32, 512), ("gradesPerPage", 1, 4),
        ("pageSeconds", 3, 60), ("textSize", 10, 48),
    ):
        d[key] = int(led.get(key, d[key]))
        if not low <= d[key] <= high:
            raise ValueError(f"led.{key} 超出范围")
    if d["width"] * d["height"] > 524288:
        raise ValueError("LED 像素点数超出范围")
    result["version"] = int(value.get("version", result["version"]))
    return result


def admin_html():
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>放学测试平台</title><style>
body{font:17px sans-serif;max-width:780px;margin:32px auto;padding:0 20px;color:#172235;background:#f1f4f8}
main{background:white;padding:28px;border-radius:14px}fieldset{margin:20px 0;padding:18px;border:1px solid #ccd5e0}
label{display:block;margin:10px 0}input{font-size:17px;padding:8px}input[type=number],input[type=text]{width:250px}
button{font-size:17px;padding:10px 20px}small{color:#576477}</style><main>
<h1>放学测试平台</h1><p>只在这台 Mac 上编辑。安卓设备定时拉取配置；班级绑卡和放学时间继续使用现有平台接口。</p>
<fieldset><legend>模块</legend>
<label>学校编号 <input id="schoolId" type="text"></label>
<label><input id="dismissalEnabled" type="checkbox"> 启用放学模块</label>
<label><input id="testMode" type="checkbox"> 测试模式：暂时跳过放学时间限制</label></fieldset>
<fieldset><legend>语音</legend>
<label>语速 <input id="speed" type="number" step="0.1" min="0.5" max="2"></label>
<label>音量（0–100） <input id="volumePercent" type="number" min="0" max="100"></label>
<label>播报遍数 <input id="repeatCount" type="number" min="1" max="10"></label>
<label>两遍间隔（秒） <input id="repeatIntervalSeconds" type="number" min="0" max="30"></label></fieldset>
<fieldset><legend>LED（控制卡接入后启用）</legend>
<label><input id="ledEnabled" type="checkbox"> 启用 LED</label>
<label>控制卡 IP <input id="controllerIp" type="text"></label>
<label>端口 <input id="controllerPort" type="number"></label>
<label>宽度 <input id="width" type="number"></label>
<label>高度 <input id="height" type="number"></label>
<label>标题 <input id="schoolTitle" type="text"></label>
<label>每页年级数 <input id="gradesPerPage" type="number"></label>
<label>切页秒数 <input id="pageSeconds" type="number"></label>
<label>字号 <input id="textSize" type="number"></label></fieldset>
<button onclick="save()">保存并下发</button><p id="status"></p>
<fieldset><legend>远程联调</legend>
<p id="deviceState">等待话机状态…</p>
<button onclick="command('led_ping')">远程检查 LED 连接</button>
<button onclick="command('led_send_page')">远程发送当前班级画面</button>
<p id="commandStatus"></p><p id="diagnostic">等待话机回传…</p>
<details><summary>最近诊断记录</summary><pre id="events" style="white-space:pre-wrap"></pre></details>
</fieldset>
<fieldset><legend>版本发布与话机配对</legend>
<p id="release">尚未发布测试版</p>
<input id="apk" type="file" accept=".apk,application/vnd.android.package-archive">
<button onclick="publish()">发布选中的 APK</button><p id="publishStatus"></p>
<p id="download"></p>
<img id="apkQr" alt="测试版安装包二维码" width="256" height="256">
<p>用话机扫描上方二维码安装测试版；安装后扫描下方二维码连接平台。临时公网地址变化时，只需重新扫描下方二维码。</p>
<img id="pairQr" alt="话机配对二维码" width="216" height="216"><p id="pairLink"></p>
</fieldset>
<small>本页仅是 Mac 测试平台；正式服务端接口需按相同字段实现。</small></main>
<script>
const id=x=>document.getElementById(x), v=x=>id(x).value, n=x=>Number(v(x));
async function load(){let r=await fetch('/api/device-config');let d=(await r.json()).data;
id('schoolId').value=d.schoolId;id('dismissalEnabled').checked=d.dismissalEnabled;
id('testMode').checked=d.testMode;
for(let k of ['speed','volumePercent','repeatCount','repeatIntervalSeconds'])id(k).value=d.voice[k];
id('ledEnabled').checked=d.led.enabled;
for(let k of ['controllerIp','controllerPort','width','height','schoolTitle','gradesPerPage','pageSeconds','textSize'])
id(k).value=d.led[k];}
async function save(){let d={schoolId:v('schoolId'),dismissalEnabled:id('dismissalEnabled').checked,
testMode:id('testMode').checked,voice:{speed:n('speed'),volumePercent:n('volumePercent'),
repeatCount:n('repeatCount'),repeatIntervalSeconds:n('repeatIntervalSeconds')},
led:{enabled:id('ledEnabled').checked,controllerIp:v('controllerIp'),controllerPort:n('controllerPort'),
width:n('width'),height:n('height'),schoolTitle:v('schoolTitle'),
gradesPerPage:n('gradesPerPage'),pageSeconds:n('pageSeconds'),textSize:n('textSize')}};
let r=await fetch('/api/device-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
let x=await r.json();id('status').textContent=r.ok?'已保存，设备下次拉取时生效（版本 '+x.data.version+'）':'保存失败：'+x.message;}
async function loadDiagnostic(){try{let r=await fetch('/api/led-diagnostic');let x=await r.json();
let d=x.data;id('diagnostic').textContent=d?(d.receivedAt+' · '+(d.success?'成功':'失败')+' · '+d.stage+' · '+d.message+' · 安卓 '+d.appVersion):'尚未收到新版话机的诊断结果';
}catch(e){id('diagnostic').textContent='诊断读取失败：'+e.message;}}
async function loadDownload(){let r=await fetch('/api/debug-apk-link');let x=await r.json();
if(x.data&&x.data.url){let a=document.createElement('a');a.href=x.data.url;a.textContent='在话机浏览器打开，下载并安装最新版 APK';
id('download').replaceChildren(a);let p=document.createElement('p');p.textContent=x.data.url;id('download').append(p);
id('apkQr').src='/api/apk-qr.png';}else{id('apkQr').hidden=true;}}
async function loadRemote(){try{let r=await fetch('/api/remote-state');let x=await r.json(),d=x.data;
let last=d.events[0];id('deviceState').textContent=last?'最近回报：'+last.receivedAt+' · 安卓 '+last.appVersion+' · '+last.type:'话机尚无回报';
let c=d.command;id('commandStatus').textContent=c?'命令 '+c.type+'：'+c.status+(c.result?' · '+c.result.message:''):'';
id('release').textContent=d.release?'已发布 '+d.release.versionName+'（版本号 '+d.release.versionCode+'） · '+d.release.publishedAt:'尚未发布测试版';
id('events').textContent=d.events.map(e=>e.receivedAt+' · '+e.type+' · '+(e.success?'成功':'失败')+' · '+e.message+' · v'+e.appVersion).join('\\n');
}catch(e){id('deviceState').textContent='远程状态读取失败：'+e.message;}}
async function command(type){let r=await fetch('/api/device-command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type})});
let x=await r.json();id('commandStatus').textContent=r.ok?'已下发，等待话机回传（最多 5 分钟）':'下发失败：'+x.message;loadRemote();}
async function publish(){let file=id('apk').files[0];if(!file){id('publishStatus').textContent='请先选择 APK';return;}
id('publishStatus').textContent='正在校验并发布…';let r=await fetch('/api/release',{method:'POST',headers:{'Content-Type':'application/vnd.android.package-archive'},body:file});
let x=await r.json();id('publishStatus').textContent=r.ok?'已发布 '+x.data.versionName+'；等待话机拉取并由现场确认安装':'发布失败：'+x.message;
loadRemote();loadDownload();}
async function loadPair(){let r=await fetch('/api/pair-link');let x=await r.json();
if(x.data.url){id('pairQr').src='/api/pair-qr.png';let a=document.createElement('a');a.href=x.data.url;a.textContent='话机配对链接';
id('pairLink').replaceChildren(a);}else{id('pairQr').hidden=true;id('pairLink').textContent='未配置公网地址';}}
load();loadDiagnostic();loadRemote();loadDownload();loadPair();setInterval(()=>{loadDiagnostic();loadRemote();},5000);</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.headers.get("X-Device-Token", "") == report_token():
            return True
        self._json(403, {"code": 403, "message": "Forbidden"})
        return False

    def _apk(self, path):
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Disposition", 'attachment; filename="dismissal-debug.apk"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as apk:
            while chunk := apk.read(65536):
                self.wfile.write(chunk)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/device-config":
            self._json(200, {"code": 200, "data": read_config()})
        elif path == "/api/device-control":
            if self._authorized():
                self._json(200, {"code": 200, "data": REMOTE.snapshot()})
        elif path.startswith("/api/releases/"):
            sha = path[len("/api/releases/"):-4] if path.endswith(".apk") else ""
            allowed = self.headers.get("X-Device-Token") == report_token() or \
                urlparse(self.path).query == "download=" + download_token()
            apk = REMOTE.releases_dir / f"{sha}.apk"
            if not allowed:
                self._json(403, {"code": 403, "message": "Forbidden"})
            elif len(sha) == 64 and all(c in "0123456789abcdef" for c in sha) and apk.is_file():
                self._apk(apk)
            else:
                self._json(404, {"code": 404, "message": "APK not found"})
        elif path == "/pair/" + PAIR_TOKEN_FILE.read_text(encoding="utf-8").strip() and PUBLIC_URL:
            body = pair_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/debug-apk/" + download_token() and APK_FILE.is_file():
            self._apk(APK_FILE)
        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/led-diagnostic", "/api/device-events"):
            self._json(405, {"code": 405, "message": "Read only"})
            return
        if not self._authorized():
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 4096:
                raise ValueError("诊断数据大小无效")
            data = json.loads(self.rfile.read(size))
            if path == "/api/device-events":
                inserted = REMOTE.record_event(data)
                self._json(200, {"code": 200, "data": {"inserted": inserted}})
                return
            if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
                raise ValueError("诊断数据格式错误")
            for key in ("stage", "message", "appVersion", "controller"):
                if not isinstance(data.get(key), str) or len(data[key]) > 500:
                    raise ValueError("诊断字段无效")
            if not isinstance(data.get("configVersion"), int):
                raise ValueError("配置版本无效")
            data["receivedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
            with CONFIG_LOCK:
                DIAGNOSTIC_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self._json(200, {"code": 200})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._json(400, {"code": 400, "message": str(error)})


def report_token():
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def download_token():
    return APK_TOKEN_FILE.read_text(encoding="utf-8").strip()


class AdminHandler(Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/admin":
            body = admin_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/led-diagnostic":
            data = json.loads(DIAGNOSTIC_FILE.read_text(encoding="utf-8")) if DIAGNOSTIC_FILE.exists() else None
            self._json(200, {"code": 200, "data": data})
        elif path == "/api/remote-state":
            self._json(200, {"code": 200, "data": REMOTE.admin_state()})
        elif path == "/api/pair-link":
            self._json(200, {"code": 200, "data": {"url": pair_url()}})
        elif path == "/api/pair-qr.png" and PUBLIC_URL:
            body = qr_png(pair_url())
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/apk-qr.png" and download_url():
            body = qr_png(download_url())
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/debug-apk-link":
            self._json(200, {"code": 200, "data": {"url": download_url()}})
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/device-command":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 512:
                    raise ValueError("命令请求大小无效")
                data = json.loads(self.rfile.read(size))
                command = REMOTE.enqueue(data.get("type"))
                self._json(200, {"code": 200, "data": command})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self._json(400, {"code": 400, "message": str(error)})
            return
        if path == "/api/release":
            temporary = STATE_FILE.parent / f"android_upload_{secrets.token_hex(8)}.apk"
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= MAX_APK_BYTES:
                    raise ValueError("APK 大小无效或超过 40 MB")
                with CONFIG_LOCK:
                    with temporary.open("wb") as output:
                        remaining = size
                        while remaining:
                            block = self.rfile.read(min(65536, remaining))
                            if not block:
                                raise ValueError("APK 上传不完整")
                            output.write(block)
                            remaining -= len(block)
                    release = REMOTE.publish(temporary)
                self._json(200, {"code": 200, "data": release})
            except (ValueError, TypeError, OSError) as error:
                self._json(400, {"code": 400, "message": str(error)})
            finally:
                temporary.unlink(missing_ok=True)
            return
        if path != "/api/device-config":
            self._json(404, {"code": 404, "message": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 8192:
                raise ValueError("请求数据大小无效")
            incoming = json.loads(self.rfile.read(size))
            with CONFIG_LOCK:
                current = read_config()
                incoming["version"] = current["version"] + 1
                saved = validate(incoming)
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                temporary = STATE_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(STATE_FILE)
            self._json(200, {"code": 200, "data": saved})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._json(400, {"code": 400, "message": str(error)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--admin-port", type=int, default=8766)
    args = parser.parse_args()
    ensure_tokens()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    admin = ThreadingHTTPServer(("127.0.0.1", args.admin_port), AdminHandler)
    threading.Thread(target=admin.serve_forever, daemon=True).start()
    print(f"Device API on 127.0.0.1:{args.port}; Mac admin on 127.0.0.1:{args.admin_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
