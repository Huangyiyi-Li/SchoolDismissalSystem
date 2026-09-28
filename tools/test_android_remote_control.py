import hashlib
import tempfile
import unittest
from pathlib import Path

from android_remote_control import RemoteControlStore


SIGNER = "a" * 64


class RemoteControlStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath("android_signer_sha256").write_text(SIGNER)
        self.time = [1000]
        self.store = RemoteControlStore(
            self.root, inspector=lambda _: {"packageName": "cn.xxt.dismissal.poc",
                                            "versionCode": 8, "versionName": "0.5.0",
                                            "signerSha256": SIGNER},
            clock=lambda: self.time[0])

    def event(self, command):
        return {"eventId": "b" * 32, "commandId": command["id"], "type": command["type"],
                "success": False, "message": "CMD_PARAM", "appVersion": "0.5.0",
                "versionCode": 8, "configVersion": 19, "controller": "192.168.1.199:5005"}

    def test_command_ack_is_idempotent_and_visible(self):
        command = self.store.enqueue("led_send_page")
        self.assertEqual(self.store.snapshot()["command"]["id"], command["id"])
        with self.assertRaisesRegex(ValueError, "上一条"):
            self.store.enqueue("led_ping")
        self.assertTrue(self.store.record_event(self.event(command)))
        self.assertFalse(self.store.record_event(self.event(command)))
        state = self.store.admin_state()
        self.assertEqual(state["command"]["status"], "completed")
        self.assertEqual(state["command"]["result"]["message"], "CMD_PARAM")
        self.assertIsNone(self.store.snapshot()["command"])
        self.assertEqual(len(state["events"]), 1)

    def test_expired_command_is_not_delivered(self):
        self.store.enqueue("led_ping")
        self.time[0] += 301
        self.assertIsNone(self.store.snapshot()["command"])
        self.assertEqual(self.store.admin_state()["command"]["status"], "expired")
        self.assertEqual(self.store.enqueue("led_send_page")["type"], "led_send_page")

    def test_release_is_immutable_and_checks_signer_and_version(self):
        apk = self.root / "test.apk"
        apk.write_bytes(b"PK-test-apk")
        release = self.store.publish(apk)
        self.assertEqual(release["sha256"], hashlib.sha256(apk.read_bytes()).hexdigest())
        self.assertEqual((self.store.root / release["downloadPath"].replace("/api/releases/", "releases/")).read_bytes(), apk.read_bytes())
        with self.assertRaisesRegex(ValueError, "版本号"):
            self.store.publish(apk)
        wrong = RemoteControlStore(self.root, inspector=lambda _: {
            "packageName": "cn.xxt.dismissal.poc", "versionCode": 9,
            "versionName": "0.5.1", "signerSha256": "c" * 64})
        with self.assertRaisesRegex(ValueError, "签名"):
            wrong.publish(apk)


if __name__ == "__main__":
    unittest.main()
