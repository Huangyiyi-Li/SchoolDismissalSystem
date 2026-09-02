import os
import tempfile
import threading
import time
import unittest
import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

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
            "led_grades_per_page": 2,
            "led_dismissed_delay_seconds": 5,
            **(values or {}),
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeBridge:
    def __init__(self):
        self.displays = []
        self.display_dimensions = []
        self.clears = []
        self.operations = []
        self.display_results = []
        self.clear_results = []

    def ping(self, ip, port):
        return BridgeResult(True, f"{ip}:{port}")

    def display(
        self,
        ip,
        port,
        pages,
        stay_seconds,
        width=1024,
        height=96,
        color_mode="single",
    ):
        self.displays.append((ip, port, list(pages), stay_seconds))
        self.display_dimensions.append((width, height))
        self.last_color_mode = color_mode
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


class FakeOperationLogger:
    def __init__(self):
        self.entries = []

    def record(self, **entry):
        self.entries.append(entry)
        return entry


class LedServiceTests(unittest.TestCase):
    def test_selected_grade_filter_only_reaches_admin_renderer_and_keeps_clubs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "201", "二年级", "二年级一班", source_order=1
            )
            db.upsert_led_class(
                "40125", 2, "301", "", "足球社团", source_order=0
            )
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_grade_filter_mode": "selected",
                        "led_visible_grades": ["二年级"],
                    }
                ),
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            classes_by_type = {
                class_type: db.get_led_classes("40125", class_type=class_type)
                for class_type in (1, 2)
            }

            with patch(
                "src.services.led_service.render_led_pages", return_value=[]
            ) as render_admin, patch(
                "src.services.led_service.render_club_led_pages", return_value=[]
            ) as render_club:
                service._render_pages_for_types(
                    classes_by_type, {}, Path(tmpdir) / "pages"
                )

            rendered_admin_classes = render_admin.call_args.args[1]
            self.assertEqual(
                [item["grade_name"] for item in rendered_admin_classes],
                ["二年级"],
            )
            self.assertEqual(
                [item["class_name"] for item in render_club.call_args.args[1]],
                ["足球社团"],
            )

    def test_preview_grade_filter_can_use_unsaved_dialog_selection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "201", "二年级", "二年级一班", source_order=1
            )
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            with patch(
                "src.services.led_service.render_led_pages", return_value=[]
            ) as render_admin:
                service.render_preview_pages(
                    Path(tmpdir) / "preview",
                    width=1024,
                    height=96,
                    grades_per_page=2,
                    regions_per_page=1,
                    show_title=True,
                    title="放学系统",
                    grade_filter_mode="selected",
                    visible_grades=["二年级"],
                )

            self.assertEqual(
                [item["grade_name"] for item in render_admin.call_args.args[1]],
                ["二年级"],
            )

    def test_hidden_grade_status_is_kept_without_resending_unchanged_led_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "201", "二年级", "二年级一班", source_order=1
            )
            bridge = FakeBridge()
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_grade_filter_mode": "selected",
                        "led_visible_grades": ["一年级"],
                    }
                ),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )

            service.mark_dismissing("201", class_type=1)

            self.assertEqual(service.get_status("201", class_type=1), "放学中")
            self.assertEqual(bridge.displays, [])
            timers.timers[0].fire()
            self.assertEqual(service.get_status("201", class_type=1), "已放学")
            self.assertEqual(bridge.displays, [])

    def test_selected_grade_missing_after_sync_clears_previous_led_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = FakeConfig({"school_id": "40125"})
            bridge = FakeBridge()
            service = LedService(
                config,
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            service.refresh()
            config.values.update(
                {
                    "led_grade_filter_mode": "selected",
                    "led_visible_grades": ["已删除年级"],
                }
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertEqual(bridge.clears, [("192.168.100.1", 5005)])

    def test_selected_grade_test_screen_uses_fallback_rows_when_catalog_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = FakeConfig(
                {
                    "school_id": "40125",
                    "led_grade_filter_mode": "selected",
                    "led_visible_grades": ["一年级", "二年级"],
                }
            )
            bridge = FakeBridge()
            service = LedService(
                config,
                DatabaseManager(os.path.join(tmpdir, "school.db")),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            with patch(
                "src.services.led_service.render_led_pages",
                return_value=[Path(tmpdir) / "fallback.bmp"],
            ) as render_admin:
                result = service.send_test_screen()

            self.assertTrue(result.ok)
            self.assertEqual(
                {item["grade_name"] for item in render_admin.call_args.args[1]},
                {"一年级", "二年级"},
            )
            self.assertEqual(len(bridge.displays), 1)

    def test_selected_grade_test_screen_uses_fallback_when_catalog_has_only_other_grades(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = FakeConfig(
                {
                    "school_id": "40125",
                    "led_grade_filter_mode": "selected",
                    "led_visible_grades": ["七年级"],
                }
            )
            bridge = FakeBridge()
            service = LedService(
                config,
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            with patch(
                "src.services.led_service.render_led_pages",
                return_value=[Path(tmpdir) / "fallback.bmp"],
            ) as render_admin:
                result = service.send_test_screen()

            self.assertTrue(result.ok)
            self.assertEqual(
                {item["grade_name"] for item in render_admin.call_args.args[1]},
                {"七年级"},
            )

    def test_dual_color_setting_reaches_bridge_and_renders_rgb_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125", "led_color_mode": "double"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertEqual(bridge.last_color_mode, "double")
            with Image.open(bridge.displays[0][2][0]) as image:
                self.assertEqual(image.mode, "RGB")

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

    def test_six_grades_per_page_renders_six_grades_on_one_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            for index in range(2, 7):
                db.upsert_led_class(
                    "40125",
                    1,
                    str(index * 100 + 1),
                    f"{index}年级",
                    f"{index}年级一班",
                    source_order=index - 1,
                )
            bridge = FakeBridge()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_grades_per_page": 6,
                    }
                ),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertEqual(len(bridge.displays), 1)
            self.assertEqual(len(list((Path(tmpdir) / "pages").glob("led-page-*.bmp"))), 1)

    def test_custom_dimensions_are_used_for_rendering_and_bridge_area(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = FakeBridge()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_width": 640,
                        "led_height": 80,
                        "led_layout_regions": 2,
                    }
                ),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )

            result = service.refresh()

            self.assertTrue(result.ok)
            self.assertEqual(bridge.display_dimensions, [(640, 80)])
            with Image.open(bridge.displays[0][2][0]) as image:
                self.assertEqual(image.size, (640, 80))

    def test_active_club_window_adds_club_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 2, "201", "", "足球社团", class_show_name="足球社团"
            )
            bridge = FakeBridge()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            service.set_dismissal_active(True, class_types={1, 2})

            result = service.refresh()

            self.assertTrue(result.ok)
            page_names = {path.name for path in service._display_pages}
            self.assertIn("led-page-01.bmp", page_names)
            self.assertIn("led-club-page-01.bmp", page_names)

    def test_club_pages_use_independent_group_and_row_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            for index in range(50):
                db.upsert_led_class(
                    "40125",
                    2,
                    str(200 + index),
                    "",
                    f"社团{index + 1}",
                    class_show_name=f"社团{index + 1}",
                    source_order=index,
                )
            bridge = FakeBridge()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_grades_per_page": 2,
                        "led_layout_regions": 1,
                        "led_club_rows_per_group": 4,
                        "led_club_groups_per_page": 5,
                    }
                ),
                db,
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            service.set_dismissal_active(True, class_types={2})

            result = service.refresh()

            self.assertTrue(result.ok)
            club_pages = [
                path for path in service._display_pages
                if path.name.startswith("led-club-page-")
            ]
            self.assertEqual(len(club_pages), 3)

    def test_dismissed_status_survives_service_restart_on_same_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            config = FakeConfig({"school_id": "40125"})
            now = datetime.datetime(2026, 7, 31, 17, 0, 0)
            first = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
                clock=lambda: now,
            )
            first.mark_dismissed("101")
            first.shutdown()

            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
                clock=lambda: now,
            )

            self.assertEqual(restarted.get_status("101"), "已放学")

    def test_dismissing_countdown_resumes_with_remaining_time_after_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            config = FakeConfig(
                {
                    "school_id": "40125",
                    "led_dismissed_delay_seconds": 5,
                }
            )
            current = [datetime.datetime(2026, 7, 31, 17, 0, 0)]
            first_timers = FakeTimerFactory()
            first = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
                clock=lambda: current[0],
                timer_factory=first_timers,
            )
            first.mark_dismissing("101")
            first.shutdown()
            current[0] += datetime.timedelta(seconds=2)
            resumed_timers = FakeTimerFactory()

            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
                clock=lambda: current[0],
                timer_factory=resumed_timers,
            )

            self.assertEqual(restarted.get_status("101"), "放学中")
            self.assertAlmostEqual(resumed_timers.timers[0].delay, 3)
            resumed_timers.timers[0].fire()
            self.assertEqual(restarted.get_status("101"), "已放学")

    def test_restored_countdown_can_finish_before_initial_window_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            config = FakeConfig(
                {
                    "school_id": "40125",
                    "led_dismissed_delay_seconds": 5,
                }
            )
            current = [datetime.datetime(2026, 7, 31, 17, 0, 0)]
            first = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
                clock=lambda: current[0],
            )
            first.mark_dismissing("101")
            first.shutdown()
            current[0] += datetime.timedelta(seconds=2)
            timers = FakeTimerFactory()
            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
                clock=lambda: current[0],
                timer_factory=timers,
                dismissal_active=None,
            )

            timers.timers[0].fire()

            self.assertEqual(restarted.get_status("101"), "已放学")

    def test_stale_restored_timer_cannot_finish_restarted_countdown_early(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            config = FakeConfig({"school_id": "40125"})
            current = [datetime.datetime(2026, 7, 31, 17, 0, 0)]
            first = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
                clock=lambda: current[0],
            )
            first.mark_dismissing("101")
            first.shutdown()
            current[0] += datetime.timedelta(seconds=2)
            timers = FakeTimerFactory()
            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
                clock=lambda: current[0],
                timer_factory=timers,
            )
            stale_timer = timers.timers[0]
            restarted.mark_dismissing("101")

            stale_timer.callback()

            self.assertEqual(restarted.get_status("101"), "放学中")

    def test_reset_statuses_removes_persisted_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            config = FakeConfig({"school_id": "40125"})
            first = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
            )
            first.mark_dismissed("101")
            first.reset_statuses()

            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
            )

            self.assertEqual(restarted.get_status("101"), "")

    def test_clearing_one_class_keeps_other_persisted_statuses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "40125", 1, "102", "一年级", "一年级二班", source_order=1
            )
            config = FakeConfig({"school_id": "40125"})
            service = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-1",
                submitter=lambda task: task(),
            )
            service.mark_dismissed("101")
            service.mark_dismissed("102")

            service.set_class_status("101", "")

            restarted = LedService(
                config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-2",
                submitter=lambda task: task(),
            )
            self.assertEqual(restarted.get_status("101"), "")
            self.assertEqual(restarted.get_status("102"), "已放学")

    def test_reset_can_clear_old_school_without_erasing_new_school_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            db.upsert_led_class(
                "50000", 1, "201", "二年级", "二年级一班", source_order=0
            )
            old_config = FakeConfig({"school_id": "40125"})
            old_service = LedService(
                old_config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-old",
                submitter=lambda task: task(),
            )
            old_service.mark_dismissed("101")
            new_config = FakeConfig({"school_id": "50000"})
            new_service = LedService(
                new_config,
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages-new",
                submitter=lambda task: task(),
            )
            new_service.mark_dismissed("201")
            old_config.values["school_id"] = "50000"

            old_service.reset_statuses(school_id="40125")

            self.assertEqual(db.get_led_class_statuses("40125", old_service._status_date.isoformat()), [])
            self.assertEqual(len(db.get_led_class_statuses("50000", old_service._status_date.isoformat())), 1)

    def test_public_dismissing_status_uses_configured_countdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timers = FakeTimerFactory()
            service = LedService(
                FakeConfig(
                    {
                        "school_id": "40125",
                        "led_dismissed_delay_seconds": 3,
                    }
                ),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )

            service.set_class_status("101", "放学中")

            self.assertEqual(timers.timers[0].delay, 3)
            timers.timers[0].fire()
            self.assertEqual(service.get_status("101"), "已放学")

    def test_legacy_dismissing_status_without_due_time_restores_as_dismissed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self.make_db(tmpdir)
            now = datetime.datetime(2026, 7, 31, 17, 0, 0)
            db.save_led_class_status(
                "40125",
                "101",
                now.date().isoformat(),
                "放学中",
            )

            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                clock=lambda: now,
            )

            self.assertEqual(service.get_status("101"), "已放学")

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

    def test_test_screen_preserves_real_class_status_and_countdown(self):
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

            self.assertEqual(service.get_status("101"), "放学中")
            self.assertFalse(status_timer.cancelled)

    def test_configured_font_sizes_are_forwarded_to_formal_renderer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = LedService(
                FakeConfig({
                    "school_id": "40125",
                    "led_title_font_size": 27,
                    "led_header_font_size": 19,
                    "led_cell_font_size": 15,
                }),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            classes = service.db.get_led_classes("40125", class_type=1)

            with patch(
                "src.services.led_service.render_led_pages", return_value=[]
            ) as render:
                service._render_pages_for_types(
                    {1: classes, 2: []}, {}, Path(tmpdir) / "pages"
                )

            self.assertEqual(render.call_args.kwargs["title_font_size"], 27)
            self.assertEqual(render.call_args.kwargs["header_font_size"], 19)
            self.assertEqual(render.call_args.kwargs["cell_font_size"], 15)

    def test_test_mode_uses_empty_isolated_statuses_and_restores_formal_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            service.mark_dismissed("101", class_type=1)

            service.set_test_mode(True)

            self.assertEqual(service.get_status("101", class_type=1), "")
            service.mark_dismissing("101", class_type=1)
            self.assertEqual(service.get_status("101", class_type=1), "放学中")
            self.assertEqual(
                service.get_status("101", class_type=1, test_mode=False),
                "已放学",
            )

            service.set_test_mode(False)

            self.assertEqual(service.get_status("101", class_type=1), "已放学")

    def test_formal_countdown_can_finish_while_test_mode_is_open(self):
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
            service.mark_dismissing("101", class_type=1)
            formal_timer = timers.timers[0]

            service.set_test_mode(True)
            formal_timer.fire()

            self.assertEqual(service.get_status("101", class_type=1), "")
            self.assertEqual(
                service.get_status("101", class_type=1, test_mode=False),
                "已放学",
            )
            service.set_test_mode(False)
            self.assertEqual(service.get_status("101", class_type=1), "已放学")

    def test_club_status_is_independent_from_administrative_class_with_same_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
            )
            service.set_dismissal_active(True, class_types={1, 2})
            service.mark_dismissed("101", class_type=1)
            service.mark_dismissing("101", class_type=2)

            self.assertEqual(service.get_status("101", class_type=1), "已放学")
            self.assertEqual(service.get_status("101", class_type=2), "放学中")

    def test_ending_one_class_type_clears_only_that_types_statuses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timers = FakeTimerFactory()
            db = self.make_db(tmpdir)
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                db,
                bridge=FakeBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                timer_factory=timers,
            )
            service.set_dismissal_active(True, class_types={1, 2})
            service.mark_dismissed("101", class_type=1)
            service.mark_dismissing("201", class_type=2)
            club_timer = timers.timers[-1]

            service.set_dismissal_active(True, class_types={1})

            self.assertEqual(service.get_status("101", class_type=1), "已放学")
            self.assertEqual(service.get_status("201", class_type=2), "")
            self.assertTrue(club_timer.cancelled)
            self.assertEqual(
                db.get_led_class_statuses(
                    "40125",
                    service._status_date.isoformat(),
                    class_type=2,
                ),
                [],
            )

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

                def display(
                    self, ip, port, pages, stay_seconds, width=1024, height=96,
                    color_mode="single",
                ):
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

    def test_failed_window_activation_is_retried_after_ten_seconds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = [datetime.datetime(2026, 8, 4, 16, 30, 0)]
            bridge = FakeBridge()
            bridge.display_results = [
                BridgeResult(False, "offline"),
                BridgeResult(True, "sent"),
            ]
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=bridge,
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                clock=lambda: current[0],
                dismissal_active=False,
            )

            service.set_dismissal_active(True)
            service.set_dismissal_active(True)
            self.assertEqual(len(bridge.displays), 1)

            current[0] += datetime.timedelta(seconds=10)
            service.set_dismissal_active(True)

            self.assertEqual(len(bridge.displays), 2)
            current[0] += datetime.timedelta(seconds=10)
            service.set_dismissal_active(True)
            self.assertEqual(len(bridge.displays), 2)

    def test_refresh_exception_is_available_in_local_operation_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            class ExplodingBridge(FakeBridge):
                def display(
                    self, ip, port, pages, stay_seconds, width=1024, height=96,
                    color_mode="single",
                ):
                    raise RuntimeError("bridge process failed")

            operation_logger = FakeOperationLogger()
            service = LedService(
                FakeConfig({"school_id": "40125"}),
                self.make_db(tmpdir),
                bridge=ExplodingBridge(),
                output_dir=Path(tmpdir) / "pages",
                submitter=lambda task: task(),
                dismissal_active=False,
                operation_logger=operation_logger,
            )

            service.set_dismissal_active(True)

            failure = next(
                entry
                for entry in operation_logger.entries
                if entry["action"] == "刷新放学节目"
            )
            self.assertEqual(failure["result"], "fail")
            self.assertIn("bridge process failed", failure["detail"])

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
