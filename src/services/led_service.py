import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .led_bridge_client import BridgeResult, JavaLedBridge
from .led_renderer import render_led_pages
from ..utils.path_utils import get_app_root


class LedService:
    STATUS_DISMISSING = "放学中"
    STATUS_DISMISSED = "已放学"

    def __init__(
        self,
        config_manager,
        db_manager,
        bridge=None,
        output_dir=None,
        submitter=None,
        clock=None,
    ):
        self.config = config_manager
        self.db = db_manager
        self.clock = clock or datetime.datetime.now
        self._status_date = self.clock().date()
        self._statuses = {}
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._schedule_lock = threading.Lock()
        self._refresh_scheduled = False
        self._refresh_requested = False
        self._shutdown_event = threading.Event()
        self._executor = None
        if submitter is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="led-output")
            self._submitter = self._executor.submit
        else:
            self._submitter = submitter

        root = Path(get_app_root())
        self.output_dir = Path(output_dir or (root / "data" / "led-pages"))
        self.bridge = bridge or JavaLedBridge(root / "led-bridge")

    def _reset_if_new_day(self):
        today = self.clock().date()
        if today != self._status_date:
            self._statuses.clear()
            self._status_date = today

    def get_status(self, class_id):
        with self._lock:
            self._reset_if_new_day()
            return self._statuses.get(str(class_id), "")

    def mark_dismissing(self, class_id):
        self.set_class_status(class_id, self.STATUS_DISMISSING)

    def mark_dismissed(self, class_id):
        self.set_class_status(class_id, self.STATUS_DISMISSED)

    def set_class_status(self, class_id, status):
        class_id = str(class_id or "").strip()
        if not class_id:
            return
        if status not in ("", self.STATUS_DISMISSING, self.STATUS_DISMISSED):
            raise ValueError(f"不支持的 LED 班级状态: {status}")
        with self._lock:
            self._reset_if_new_day()
            if self._statuses.get(class_id, "") == status:
                return
            self._statuses[class_id] = status
        self.refresh_async()

    def reset_statuses(self):
        with self._lock:
            self._statuses.clear()
            self._status_date = self.clock().date()

    def refresh_async(self):
        if self._shutdown_event.is_set() or not self.config.get("led_enabled", False):
            return None
        with self._schedule_lock:
            if self._refresh_scheduled:
                self._refresh_requested = True
                return None
            self._refresh_scheduled = True
        try:
            return self._submitter(self._run_refresh_once)
        except Exception:
            with self._schedule_lock:
                self._refresh_scheduled = False
            raise

    def _run_refresh_once(self):
        result = None
        if not self._shutdown_event.is_set():
            try:
                result = self.refresh()
                self._log_failed_result("刷新", result)
            except Exception as exc:
                print(f"[LED] Refresh error: {exc}")

        with self._schedule_lock:
            should_resubmit = (
                self._refresh_requested and not self._shutdown_event.is_set()
            )
            self._refresh_requested = False
            if not should_resubmit:
                self._refresh_scheduled = False
        if should_resubmit:
            try:
                # Submit at the executor tail so an already queued clear/barrier
                # operation is never bypassed by the coalesced refresh.
                self._submitter(self._run_refresh_once)
            except Exception as exc:
                with self._schedule_lock:
                    self._refresh_scheduled = False
                print(f"[LED] Failed to resubmit refresh: {exc}")
        return result

    def refresh(self, ip=None, port=None, title=None, stay_seconds=None):
        school_id = self.config.get("school_id")
        classes = self.db.get_led_classes(school_id)
        if not classes:
            with self._operation_lock:
                return self.bridge.clear(
                    ip or self.config.get("led_controller_ip", "192.168.100.1"),
                    int(port or self.config.get("led_controller_port", 5005)),
                )

        with self._lock:
            self._reset_if_new_day()
            statuses = dict(self._statuses)
        with self._operation_lock:
            pages = render_led_pages(
                title or self.config.get("led_school_title", "数智家校\n放学系统"),
                classes,
                statuses,
                self.output_dir,
                width=int(self.config.get("led_width", 1024)),
                height=int(self.config.get("led_height", 96)),
                grades_per_page=2,
            )
            result = self.bridge.display(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                stay_seconds=float(stay_seconds or self.config.get("led_page_seconds", 5)),
            )
        if not result.ok:
            print(f"[LED] Push failed: {result.message}")
        return result

    def test_connection(self, ip=None, port=None):
        with self._operation_lock:
            return self.bridge.ping(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
            )

    def clear_async(self, ip=None, port=None):
        target_ip = ip or self.config.get("led_controller_ip", "192.168.100.1")
        target_port = int(port or self.config.get("led_controller_port", 5005))

        def clear():
            try:
                with self._operation_lock:
                    result = self.bridge.clear(target_ip, target_port)
                self._log_failed_result("清屏", result)
                return result
            except Exception as exc:
                print(f"[LED] Clear error: {exc}")
                return BridgeResult(False, str(exc))

        return self._submitter(clear)

    def send_test_screen(self, ip=None, port=None, title=None, stay_seconds=None):
        school_id = self.config.get("school_id")
        classes = self.db.get_led_classes(school_id)
        if classes:
            statuses = {
                str(item["class_id"]): (
                    self.STATUS_DISMISSING if index % 2 == 0 else self.STATUS_DISMISSED
                )
                for index, item in enumerate(classes)
            }
        else:
            classes = [
                {
                    "class_id": "LED-TEST-1",
                    "grade_name": "测试",
                    "class_name": "测试一班",
                    "class_show_name": "1班",
                    "source_order": 0,
                }
            ]
            statuses = {"LED-TEST-1": "连接正常"}

        with self._operation_lock:
            pages = render_led_pages(
                title or self.config.get("led_school_title", "数智家校\n放学系统"),
                classes,
                statuses,
                self.output_dir,
                width=int(self.config.get("led_width", 1024)),
                height=int(self.config.get("led_height", 96)),
                grades_per_page=2,
            )
            return self.bridge.display(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                stay_seconds=float(stay_seconds or self.config.get("led_page_seconds", 5)),
            )

    def shutdown(self):
        self._shutdown_event.set()
        with self._schedule_lock:
            self._refresh_requested = False
        if hasattr(self.bridge, "shutdown"):
            self.bridge.shutdown()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _log_failed_result(action, result):
        if result is not None and not result.ok:
            print(f"[LED] {action}失败: {result.message}")
