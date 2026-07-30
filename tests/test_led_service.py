import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import DatabaseManager
from src.services.led_bridge_client import BridgeResult
from src.services.led_renderer import render_led_pages as real_render_led_pages
from src.services.led_service import LedService


class FakeConfig:
    def __init__(self, values=None):
        self.values = {
            "led_enabled": True,
            "led_controller_ip": "192.168.100.1",
            "led_controller_port": 5005,
            "led_school_title": "健康路小学\n数智家校\n放学系统",
            "led_page_seconds": 5,
            "led_dismissed_delay_seconds": 5,
            **(values or {}),
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeBridge:
    def __init__(self):
        self.displays = []
        self.clears = []
        self.operations = []
        self.display_results = []
        self.clear_results = []

    def ping(self, ip, port):
        return BridgeResult(True, f"{ip}:{port}")

    def display(self, ip, port, pages, stay_seconds):
        self.displays.append((ip, port, list(pages), stay_seconds))
        self.operations.append(("display", ip, port))
        if self.display_results:
            return self.display_results.pop(0)
        return BridgeResult(True, "sent")

    def clear(self, ip, port):
        self.clears.append((ip, port))
        self.operations.append(("clear", ip, port))
        if self.clear_results:
            return self.clear_results.pop(0)
        return BridgeResult(True, "cleared")


class FakeTimer:
    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


class FakeTimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, delay, callback):
        timer = FakeTimer(delay, callback)
        self.timers.append(timer)
        return timer


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

    def test_mark_dismissing_automatically_changes_to_dismissed_after_configured_delay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_dismissed_delay_seconds": 3,
                    }
                ),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )

            service.mark_dismissing("101")

            self.assertEqual(service.get_status("101"), "放学中")
            self.assertEqual(timers.timers[0].delay, 3)
            self.assertTrue(timers.timers[0].started)

            timers.timers[0].fire()

            self.assertEqual(service.get_status("101"), "已放学")
            self.assertEqual(len(bridge.displays), 2)

    def test_repeated_swipe_restarts_auto_dismissed_countdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )

            service.mark_dismissing("101")
            first_timer = timers.timers[0]
            service.mark_dismissing("101")

            self.assertTrue(first_timer.cancelled)
            self.assertEqual(len(timers.timers), 2)
            first_timer.fire()
            self.assertEqual(service.get_status("101"), "放学中")
            timers.timers[1].fire()
            self.assertEqual(service.get_status("101"), "已放学")

    def test_multiple_pages_are_sent_one_at_a_time_and_rotated_by_host_timer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            for index in range(2, 6):
                db.upsert_led_class(
                    "40125",
                    1,
                    str(index * 100 + 1),
                    f"{index}年级",
                    f"{index}年级一班",
                    source_order=index - 1,
                )
            bridge = FakeBridge()
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig({"school_id": "40125", "led_page_seconds": 4}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertIn("3 个 LED 页面", result.message)
            self.assertEqual(len(bridge.displays), 1)
            self.assertEqual(len(bridge.displays[0][2]), 1)
            self.assertEqual(bridge.displays[0][2][0].name, "led-page-01.bmp")
            self.assertEqual(timers.timers[0].delay, 4)

            timers.timers[0].fire()

            self.assertEqual(len(bridge.displays), 2)
            self.assertEqual(bridge.displays[1][2][0].name, "led-page-02.bmp")

    def test_reset_and_restore_clears_status_and_deletes_dynamic_area(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timers = FakeTimerFactory()
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )
            service.mark_dismissing("101")

            result = service.reset_and_restore()

            self.assertTrue(result.ok)
            self.assertEqual(service.get_status("101"), "")
            self.assertTrue(timers.timers[0].cancelled)
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])

    def test_test_screen_clears_real_class_status_and_countdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )
            service.mark_dismissing("101")
            status_timer = timers.timers[0]

            service.send_test_screen()

            self.assertEqual(service.get_status("101"), "")
            self.assertTrue(status_timer.cancelled)

    def test_page_files_are_not_rewritten_while_bridge_is_reading_them(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            for index in range(2, 4):
                db.upsert_led_class(
                    "40125",
                    1,
                    str(index * 100 + 1),
                    f"{index}年级",
                    f"{index}年级一班",
                    source_order=index - 1,
                )
            timers = FakeTimerFactory()

            class BlockingBridge(FakeBridge):
                def __init__(self):
                    super().__init__()
                    self.call_count = 0
                    self.in_display = False
                    self.entered = threading.Event()
                    self.release = threading.Event()

                def display(self, ip, port, pages, stay_seconds):
                    self.call_count += 1
                    if self.call_count == 2:
                        self.in_display = True
                        self.entered.set()
                        self.release.wait(timeout=2)
                        self.in_display = False
                    return super().display(ip, port, pages, stay_seconds)

            bridge = BlockingBridge()
            overlap = []

            def checked_render(*args, **kwargs):
                overlap.append(bridge.in_display)
                return real_render_led_pages(*args, **kwargs)

            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )
            with patch("src.services.led_service.render_led_pages", checked_render):
                service.refresh()
                rotation = threading.Thread(target=timers.timers[0].fire)
                rotation.start()
                self.assertTrue(bridge.entered.wait(timeout=1))
                refresh = threading.Thread(target=service.refresh)
                refresh.start()
                time.sleep(0.05)
                bridge.release.set()
                rotation.join(timeout=2)
                refresh.join(timeout=2)

            self.assertFalse(any(overlap))

    def test_leaving_dismissal_window_restores_original_program_only_once(self):
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

            service.set_dismissal_active(False)
            service.set_dismissal_active(False)

            self.assertEqual(service.get_status("101"), "")
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])
            service.mark_dismissing("101")
            self.assertEqual(service.get_status("101"), "")
            self.assertEqual(len(bridge.displays), 1)

    def test_leaving_window_cancels_page_rotation_before_restore_task_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "201", "二年级", "二年级一班", source_order=1
            )
            db.upsert_led_class(
                "40125", 1, "301", "三年级", "三年级一班", source_order=2
            )
            timers = FakeTimerFactory()
            queued = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=queued.append,
                timer_factory=timers,
            )
            service.refresh()
            rotation_timer = timers.timers[0]

            service.set_dismissal_active(False)

            self.assertTrue(rotation_timer.cancelled)
            self.assertEqual(len(queued), 1)

    def test_failed_window_restore_is_retried_on_next_state_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            bridge.clear_results = [
                BridgeResult(False, "offline"),
                BridgeResult(True, "cleared"),
            ]
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            service.set_dismissal_active(False)
            service.set_dismissal_active(False)

            self.assertEqual(len(bridge.clears), 2)

    def test_stale_restore_cannot_cancel_newer_inactive_restore_request(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            queued = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=queued.append,
            )

            service.set_dismissal_active(False)
            stale_restore = queued.pop(0)
            service.set_dismissal_active(True)
            service.set_dismissal_active(False)
            stale_restore()
            queued_before_retry = len(queued)

            service.set_dismissal_active(False)

            self.assertEqual(len(queued), queued_before_retry + 1)
            queued[-1]()
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])

    def test_entering_window_reports_that_it_already_scheduled_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queued = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=queued.append,
                dismissal_active=False,
            )

            refresh_scheduled = service.set_dismissal_active(True)

            self.assertTrue(refresh_scheduled)
            self.assertEqual(len(queued), 1)

    def test_rotation_continues_after_transient_send_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "201", "二年级", "二年级一班", source_order=1
            )
            db.upsert_led_class(
                "40125", 1, "301", "三年级", "三年级一班", source_order=2
            )
            bridge = FakeBridge()
            bridge.display_results = [
                BridgeResult(True, "sent"),
                BridgeResult(False, "temporary offline"),
            ]
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )
            service.refresh()

            timers.timers[0].fire()

            self.assertEqual(len(timers.timers), 2)
            self.assertTrue(timers.timers[1].started)

    def test_superseded_display_request_does_not_write_controller(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            page = Path(tmpdir) / "page.bmp"
            page.write_bytes(b"BM")

            class SupersedingLock:
                def __enter__(self):
                    service._stop_display_session()

                def __exit__(self, exc_type, exc, traceback):
                    return False

            service._operation_lock = SupersedingLock()

            service._start_display_session(
                "192.168.100.1", 5005, [page], stay_seconds=5
            )

            self.assertEqual(bridge.displays, [])

    def test_superseded_empty_catalog_refresh_does_not_clear_newer_display(self):
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

            class SupersedingLock:
                def __enter__(self):
                    service._stop_display_session()

                def __exit__(self, exc_type, exc, traceback):
                    return False

            service._operation_lock = SupersedingLock()

            service.refresh()

            self.assertEqual(bridge.clears, [])

    def test_refresh_that_started_before_window_end_cannot_reopen_live_display(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            queued = []
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=queued.append,
            )
            render_entered = threading.Event()
            release_render = threading.Event()

            def paused_render(*args, **kwargs):
                render_entered.set()
                release_render.wait(timeout=2)
                return real_render_led_pages(*args, **kwargs)

            with patch("src.services.led_service.render_led_pages", paused_render):
                refresh = threading.Thread(target=service.refresh)
                refresh.start()
                self.assertTrue(render_entered.wait(timeout=1))
                service.set_dismissal_active(False)
                release_render.set()
                refresh.join(timeout=2)

            for task in list(queued):
                task()

            self.assertEqual(bridge.displays, [])
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])


if __name__ == "__main__":
    unittest.main()
