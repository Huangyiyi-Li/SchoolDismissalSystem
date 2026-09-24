"""Mac-only test platform for Android dismissal settings missing from the live API.

Class/card data and school schedules remain on the existing rest.xxt.cn APIs.
Run: python3 tools/android_mock_platform.py
Open http://127.0.0.1:8766/admin on the Mac to edit the test settings.
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


STATE_FILE = Path(__file__).resolve().parent.parent / ".local" / "android_mock_config.json"
CONFIG_LOCK = threading.Lock()
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
load();</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/device-config":
            self._json(200, {"code": 200, "data": read_config()})
        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def do_POST(self):
        self._json(405, {"code": 405, "message": "Read only"})


class AdminHandler(Handler):
    def do_GET(self):
        if urlparse(self.path).path == "/admin":
            body = admin_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/device-config":
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
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    admin = ThreadingHTTPServer(("127.0.0.1", args.admin_port), AdminHandler)
    threading.Thread(target=admin.serve_forever, daemon=True).start()
    print(f"Device API on 127.0.0.1:{args.port}; Mac admin on 127.0.0.1:{args.admin_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
