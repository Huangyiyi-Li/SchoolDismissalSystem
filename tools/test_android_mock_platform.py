import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import android_mock_platform as platform
from android_remote_control import RemoteControlStore


class RemotePlatformHttpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saved = {name: getattr(platform, name) for name in
                      ("STATE_FILE", "DIAGNOSTIC_FILE", "TOKEN_FILE", "APK_TOKEN_FILE",
                       "PAIR_TOKEN_FILE", "PAIR_CODE_FILE", "APK_FILE", "PUBLIC_URL", "REMOTE")}
        platform.STATE_FILE = self.root / "config.json"
        platform.DIAGNOSTIC_FILE = self.root / "diagnostic.json"
        platform.TOKEN_FILE = self.root / "report_token"
        platform.APK_TOKEN_FILE = self.root / "download_token"
        platform.PAIR_TOKEN_FILE = self.root / "pair_token"
        platform.PAIR_CODE_FILE = self.root / "pair_code"
        platform.APK_FILE = self.root / "bootstrap.apk"
        platform.APK_FILE.write_bytes(b"PK-bootstrap")
        platform.PUBLIC_URL = "https://example.com"
        platform.REMOTE = RemoteControlStore(self.root, inspector=lambda _: {
            "packageName": "cn.xxt.dismissal.poc", "versionCode": 8,
            "versionName": "0.5.0", "signerSha256": "a" * 64})
        platform.REMOTE.signer_file.write_text("a" * 64)
        platform.ensure_tokens()
        self.device = ThreadingHTTPServer(("127.0.0.1", 0), platform.Handler)
        self.admin = ThreadingHTTPServer(("127.0.0.1", 0), platform.AdminHandler)
        for server in (self.device, self.admin):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(self.stop_servers)

    def stop_servers(self):
        for server in (self.device, self.admin):
            server.shutdown()
            server.server_close()
        for key, value in self.saved.items():
            setattr(platform, key, value)

    def request(self, server, path, data=None, token=False, content_type="application/json"):
        address = "http://127.0.0.1:" + str(server.server_address[1]) + path
        headers = {"Content-Type": content_type}
        if token:
            headers["X-Device-Token"] = platform.report_token()
        request = urllib.request.Request(address, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()

    def test_remote_command_result_and_release(self):
        with self.assertRaises(urllib.error.HTTPError) as denial:
            self.request(self.device, "/api/device-control")
        self.assertEqual(denial.exception.code, 403)

        body = json.dumps({"type": "led_ping"}).encode()
        status, response = self.request(self.admin, "/api/device-command", body)
        self.assertEqual(status, 200)
        command = json.loads(response)["data"]
        status, response = self.request(self.device, "/api/device-control", token=True)
        self.assertEqual(json.loads(response)["data"]["command"]["id"], command["id"])

        event = {"eventId": "b" * 32, "commandId": command["id"], "type": "led_ping",
                 "success": True, "message": "已连接", "appVersion": "0.5.0",
                 "versionCode": 8, "configVersion": 19, "controller": "192.168.1.199:5005"}
        self.request(self.device, "/api/device-events", json.dumps(event).encode(), token=True)
        state = json.loads(self.request(self.admin, "/api/remote-state")[1])["data"]
        self.assertEqual(state["command"]["status"], "completed")
        self.assertEqual(state["events"][0]["message"], "已连接")

        apk = b"PK-new-apk"
        status, response = self.request(self.admin, "/api/release", apk,
                                        content_type="application/vnd.android.package-archive")
        self.assertEqual(status, 200)
        release = json.loads(response)["data"]
        with self.assertRaises(urllib.error.HTTPError) as denial:
            self.request(self.device, release["downloadPath"])
        self.assertEqual(denial.exception.code, 403)
        status, downloaded = self.request(self.device, release["downloadPath"], token=True)
        self.assertEqual(downloaded, apk)
        self.assertEqual(json.loads(self.request(self.device, "/api/device-control", token=True)[1])
                         ["data"]["release"]["versionCode"], 8)

    def test_pair_page_is_guarded_and_qr_is_png(self):
        with self.assertRaises(urllib.error.HTTPError) as denial:
            self.request(self.device, "/pair/wrong")
        self.assertEqual(denial.exception.code, 404)
        pair = json.loads(self.request(self.admin, "/api/pair-link")[1])["data"]["url"]
        status, body = self.request(self.device, pair.removeprefix("https://example.com"))
        self.assertEqual(status, 200)
        self.assertIn(b"xxtdismissal://connect", body)
        status, qr = self.request(self.admin, "/api/pair-qr.png")
        self.assertEqual(status, 200)
        self.assertTrue(qr.startswith(b"\x89PNG"))
        status, apk_qr = self.request(self.admin, "/api/apk-qr.png")
        self.assertEqual(status, 200)
        self.assertTrue(apk_qr.startswith(b"\x89PNG"))

    def test_manual_install_and_pairing(self):
        status, landing = self.request(self.device, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"/connect", landing)
        self.assertNotIn(platform.report_token().encode(), landing)
        info = json.loads(self.request(self.admin, "/api/setup-info")[1])["data"]
        self.assertEqual(info["url"], "https://example.com/")
        self.assertEqual(len(info["code"]), 8)
        with self.assertRaises(urllib.error.HTTPError) as denial:
            self.request(self.device, "/connect", b"code=WRONG123",
                         content_type="application/x-www-form-urlencoded")
        self.assertEqual(denial.exception.code, 403)
        status, paired = self.request(self.device, "/connect",
                                      ("code=" + info["code"].lower()).encode(),
                                      content_type="application/x-www-form-urlencoded")
        self.assertEqual(status, 200)
        self.assertIn(b"xxtdismissal://connect", paired)

    def test_admin_script_parses(self):
        if shutil.which("node") is None:
            self.skipTest("Node.js unavailable")
        script = platform.admin_html().split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(["node", "--check", "-"], input=script,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
