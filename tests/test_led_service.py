import os
import tempfile
import unittest
from pathlib import Path

from src.database import DatabaseManager
from src.services.led_bridge_client import BridgeResult
from src.services.led_service import LedService


class FakeConfig:
    def __init__(self, values=None):
        self.values = {
            "led_enabled": True,
            "led_controller_ip": "192.168.100.1",
            "led_controller_port": 5005,
            "led_school_title": "健康路小学\n数智家校\n放学系统",
            "led_page_seconds": 5,
            **(values or {}),
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeBridge:
    def __init__(self):
        self.displays = []
        self.clears = []
        self.operations = []

    def ping(self, ip, port):
        return BridgeResult(True, f"{ip}:{port}")

    def display(self, ip, port, pages, stay_seconds):
        self.displays.append((ip, port, list(pages), stay_seconds))
        self.operations.append(("display", ip, port))
        return BridgeResult(True, "sent")

    def clear(self, ip, port):
        self.clears.append((ip, port))
        self.operations.append(("clear", ip, port))
        return BridgeResult(True, "cleared")


class LedServiceTests(unittest.TestCase):
    def make_db(self, tmpdir):
        db = DatabaseManager(os.path.join(tmpdir, "school.db"))
        db.upsert_led_class("40125", 1, "101", "一年级", "一年级一班", source_order=0)
        return db

    def test_mark_dismissing_renders_and_sends_current_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            service.mark_dismissing("101")

            self.assertEqual(service.get_status("101"), "放学中")
            self.assertEqual(len(bridge.displays), 1)
            self.assertEqual(bridge.displays[0][0:2], ("192.168.100.1", 5005))
            self.assertTrue(bridge.displays[0][2][0].is_file())

    def test_disabled_led_keeps_status_but_does_not_send(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125", "led_enabled": False}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            service.mark_dismissing("101")

            self.assertEqual(service.get_status("101"), "放学中")
            self.assertEqual(bridge.displays, [])

    def test_repeated_same_status_does_not_resend_identical_screen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            service.mark_dismissing("101")
            service.mark_dismissing("101")

            self.assertEqual(len(bridge.displays), 1)

    def test_empty_catalog_clears_stale_dynamic_area(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            db = DatabaseManager(os.path.join(tmpdir, "school.db"))
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])

    def test_burst_updates_submit_only_one_worker_with_one_pending_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            db = self.make_db(tmpdir)
            db.upsert_led_class("40125", 1, "102", "一年级", "一年级二班", source_order=1)
            tasks = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=tasks.append,
            )

            service.mark_dismissing("101")
            service.mark_dismissing("102")

            self.assertEqual(len(tasks), 1)
            tasks[0]()
            self.assertEqual(len(bridge.displays), 1)
            self.assertEqual(len(tasks), 2)
            tasks[1]()
            self.assertEqual(len(bridge.displays), 2)

    def test_shutdown_cancels_pending_refresh_before_bridge_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            tasks = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=tasks.append,
            )
            service.mark_dismissing("101")

            service.shutdown()
            tasks[0]()

            self.assertEqual(bridge.displays, [])

    def test_queued_clear_stays_before_coalesced_followup_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            tasks = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=tasks.append,
            )
            service.mark_dismissing("101")
            service.clear_async("192.168.100.1", 5005)
            service.mark_dismissed("101")

            tasks.pop(0)()
            tasks.pop(0)()
            tasks.pop(0)()

            self.assertEqual(
                [operation[0] for operation in bridge.operations],
                ["display", "clear", "display"],
            )


if __name__ == "__main__":
    unittest.main()
