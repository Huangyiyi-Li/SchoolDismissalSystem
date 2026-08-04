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
    WINDOW_REFRESH_RETRY_SECONDS = 10

    def __init__(
        self,
        config_manager,
        db_manager,
        bridge=None,
        output_dir=None,
        submitter=None,
        clock=None,
        timer_factory=None,
        dismissal_active=True,
        operation_logger=None,
    ):
        self.config = config_manager
        self.db = db_manager
        self.clock = clock or datetime.datetime.now
        self._status_date = self.clock().date()
        self._statuses = {}
        self._status_timers = {}
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._page_files_lock = threading.Lock()
        self._schedule_lock = threading.Lock()
        self._timer_factory = timer_factory or threading.Timer
        self.operation_logger = operation_logger
        self._dismissal_active = bool(dismissal_active)
        self._dismissal_state_initialized = dismissal_active is not None
        self._display_timer = None
        self._display_generation = 0
        self._display_pages = []
        self._display_index = 0
        self._display_target = None
        self._display_interval = 5.0
        self._window_restore_pending = False
        self._window_restore_in_flight = False
        self._window_restore_epoch = 0
        self._window_refresh_pending = False
        self._next_window_refresh_retry_at = None
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
        self._restore_persisted_statuses()

    def _school_id(self):
        value = self.config.get("school_id")
        return str(value).strip() if value is not None else ""

    def _persist_status_locked(self, class_id, status, dismiss_due_at=None):
        school_id = self._school_id()
        if not school_id:
            return
        self.db.save_led_class_status(
            school_id,
            class_id,
            self._status_date.isoformat(),
            status,
            dismiss_due_at.isoformat() if dismiss_due_at else None,
        )

    def _clear_persisted_statuses_locked(self, school_id=None):
        school_id = str(school_id or self._school_id()).strip()
        if school_id:
            self.db.clear_led_class_statuses(school_id)

    def _delete_persisted_status_locked(self, class_id):
        school_id = self._school_id()
        if school_id:
            self.db.delete_led_class_status(
                school_id,
                class_id,
                self._status_date.isoformat(),
            )

    def _restore_persisted_statuses(self):
        school_id = self._school_id()
        if not school_id:
            return
        now = self.clock()
        rows = self.db.get_led_class_statuses(school_id, now.date().isoformat())
        with self._lock:
            for row in rows:
                class_id = str(row.get("class_id") or "").strip()
                status = row.get("status")
                if not class_id or status not in (
                    self.STATUS_DISMISSING,
                    self.STATUS_DISMISSED,
                ):
                    continue
                due_raw = row.get("dismiss_due_at")
                if status == self.STATUS_DISMISSING:
                    if not due_raw:
                        self._statuses[class_id] = self.STATUS_DISMISSED
                        self._persist_status_locked(
                            class_id,
                            self.STATUS_DISMISSED,
                        )
                        continue
                    try:
                        due_at = datetime.datetime.fromisoformat(due_raw)
                    except (TypeError, ValueError):
                        due_at = now
                    remaining = (due_at - now).total_seconds()
                    if remaining <= 0:
                        self._statuses[class_id] = self.STATUS_DISMISSED
                        self._persist_status_locked(
                            class_id,
                            self.STATUS_DISMISSED,
                        )
                        continue
                    self._statuses[class_id] = status
                    timer = self._make_status_timer(remaining, class_id)
                    self._status_timers[class_id] = timer
                    timer.start()
                else:
                    self._statuses[class_id] = status

    def _reset_if_new_day(self):
        today = self.clock().date()
        if today != self._status_date:
            self._cancel_all_status_timers_locked()
            self._statuses.clear()
            self._clear_persisted_statuses_locked()
            self._status_date = today

    def get_status(self, class_id):
        with self._lock:
            self._reset_if_new_day()
            return self._statuses.get(str(class_id), "")

    def mark_dismissing(self, class_id):
        class_id = str(class_id or "").strip()
        if not class_id:
            return False
        with self._lock:
            self._reset_if_new_day()
            if not self._dismissal_active:
                return False
            self._cancel_status_timer_locked(class_id)
            changed = self._statuses.get(class_id, "") != self.STATUS_DISMISSING
            self._statuses[class_id] = self.STATUS_DISMISSING
            delay = float(self.config.get("led_dismissed_delay_seconds", 5))
            dismiss_due_at = self.clock() + datetime.timedelta(seconds=delay)
            self._persist_status_locked(
                class_id,
                self.STATUS_DISMISSING,
                dismiss_due_at,
            )
            timer = self._make_status_timer(delay, class_id)
            self._status_timers[class_id] = timer
            timer.start()
        if changed:
            self.refresh_async()
        return True

    def mark_dismissed(self, class_id):
        class_id = str(class_id or "").strip()
        if not class_id:
            return False
        with self._lock:
            self._cancel_status_timer_locked(class_id)
        self.set_class_status(class_id, self.STATUS_DISMISSED)
        return True

    def _complete_dismissal(self, class_id, timer):
        with self._lock:
            if (
                self._status_timers.get(class_id) is not timer
                or (
                    not self._dismissal_active
                    and self._dismissal_state_initialized
                )
                or self._shutdown_event.is_set()
            ):
                return
            self._status_timers.pop(class_id, None)
            if self._statuses.get(class_id) != self.STATUS_DISMISSING:
                return
            self._statuses[class_id] = self.STATUS_DISMISSED
            self._persist_status_locked(class_id, self.STATUS_DISMISSED)
        self.refresh_async()

    def set_class_status(self, class_id, status):
        class_id = str(class_id or "").strip()
        if not class_id:
            return
        if status not in ("", self.STATUS_DISMISSING, self.STATUS_DISMISSED):
            raise ValueError(f"不支持的 LED 班级状态: {status}")
        if status == self.STATUS_DISMISSING:
            return self.mark_dismissing(class_id)
        with self._lock:
            self._reset_if_new_day()
            if self._statuses.get(class_id, "") == status:
                return
            if status:
                self._statuses[class_id] = status
                self._persist_status_locked(class_id, status)
            else:
                self._statuses.pop(class_id, None)
                self._delete_persisted_status_locked(class_id)
        self.refresh_async()

    def reset_statuses(self, school_id=None):
        with self._lock:
            self._cancel_all_status_timers_locked()
            self._statuses.clear()
            self._clear_persisted_statuses_locked(school_id=school_id)
            self._status_date = self.clock().date()

    def set_dismissal_active(self, active):
        active = bool(active)
        should_retry_refresh = False
        with self._lock:
            if self._dismissal_state_initialized and self._dismissal_active == active:
                if active:
                    should_retry_refresh = bool(
                        self._window_refresh_pending
                        and (
                            self._next_window_refresh_retry_at is None
                            or self.clock() >= self._next_window_refresh_retry_at
                        )
                    )
                else:
                    self._queue_window_restore()
                if not should_retry_refresh:
                    return False
            else:
                self._dismissal_state_initialized = True
                self._dismissal_active = active
                self._window_restore_epoch += 1
        if active:
            with self._lock:
                self._window_restore_pending = False
                self._window_refresh_pending = True
                self._next_window_refresh_retry_at = self.clock() + datetime.timedelta(
                    seconds=self.WINDOW_REFRESH_RETRY_SECONDS
                )
            self.refresh_async()
            if not should_retry_refresh:
                self._record_operation(
                    "时段切换",
                    "进入放学时段",
                    result="info",
                    detail="已安排发送放学节目",
                )
            return not should_retry_refresh
        with self._lock:
            self._window_refresh_pending = False
            self._next_window_refresh_retry_at = None
        self.reset_statuses()
        had_session, _ = self._stop_display_session()
        with self._lock:
            self._window_restore_pending = bool(
                self.config.get("led_enabled", False) or had_session
            )
        self._queue_window_restore()
        self._record_operation(
            "时段切换",
            "离开放学时段",
            result="info",
            detail="已清空班级状态并安排恢复原节目",
        )
        return False

    def _queue_window_restore(self):
        with self._lock:
            if (
                not self._window_restore_pending
                or self._window_restore_in_flight
                or self._dismissal_active
                or self._shutdown_event.is_set()
            ):
                return None
            self._window_restore_in_flight = True
            restore_epoch = self._window_restore_epoch
            generation = self._display_generation
            target_ip = self.config.get("led_controller_ip", "192.168.100.1")
            target_port = int(self.config.get("led_controller_port", 5005))

        def restore():
            superseded = False
            try:
                with self._operation_lock:
                    with self._lock:
                        superseded = (
                            self._dismissal_active
                            or generation != self._display_generation
                        )
                    if superseded:
                        result = BridgeResult(True, "恢复请求已被新的显示状态取代")
                    else:
                        result = self.bridge.clear(target_ip, target_port)
            except Exception as exc:
                result = BridgeResult(False, str(exc))
            with self._lock:
                self._window_restore_in_flight = False
                if result.ok and restore_epoch == self._window_restore_epoch:
                    self._window_restore_pending = False
            self._log_failed_result("恢复原节目", result)
            self._record_operation(
                "LED 屏",
                "恢复原节目",
                target=f"{target_ip}:{target_port}",
                result="success" if result.ok else "fail",
                detail=result.message,
            )
            return result

        try:
            return self._submitter(restore)
        except Exception:
            with self._lock:
                self._window_restore_in_flight = False
            raise

    def refresh_async(self):
        if (
            self._shutdown_event.is_set()
            or not self.config.get("led_enabled", False)
            or not self._dismissal_active
        ):
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
                result = BridgeResult(False, str(exc))

        with self._lock:
            if self._dismissal_active:
                if result is not None and result.ok:
                    self._window_refresh_pending = False
                    self._next_window_refresh_retry_at = None
                else:
                    self._window_refresh_pending = True
                    self._next_window_refresh_retry_at = self.clock() + datetime.timedelta(
                        seconds=self.WINDOW_REFRESH_RETRY_SECONDS
                    )

        if result is not None:
            self._record_operation(
                "LED 屏",
                "刷新放学节目",
                target=self._controller_target(),
                result="success" if result.ok else "fail",
                detail=result.message,
            )

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
        with self._lock:
            if not self._dismissal_active:
                return BridgeResult(True, "非放学时段，未控制 LED 屏")
        school_id = self.config.get("school_id")
        classes = self.db.get_led_classes(school_id)
        if not classes:
            _, generation = self._stop_display_session()
            with self._operation_lock:
                with self._lock:
                    superseded = (
                        generation != self._display_generation
                        or not self._dismissal_active
                    )
                if superseded:
                    return BridgeResult(True, "清除请求已被新的显示状态取代")
                return self.bridge.clear(
                    ip or self.config.get("led_controller_ip", "192.168.100.1"),
                    int(port or self.config.get("led_controller_port", 5005)),
                )

        with self._lock:
            self._reset_if_new_day()
            statuses = dict(self._statuses)
        with self._page_files_lock:
            pages = render_led_pages(
                title or self.config.get("led_school_title", "数智家校\n放学系统"),
                classes,
                statuses,
                self.output_dir,
                width=int(self.config.get("led_width", 1024)),
                height=int(self.config.get("led_height", 96)),
                grades_per_page=int(self.config.get("led_grades_per_page", 2)),
            )
            result = self._start_display_session(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                float(stay_seconds or self.config.get("led_page_seconds", 5)),
                require_dismissal_active=True,
            )
        if not result.ok:
            print(f"[LED] Push failed: {result.message}")
        return result

    def test_connection(self, ip=None, port=None):
        with self._operation_lock:
            target_ip = ip or self.config.get("led_controller_ip", "192.168.100.1")
            target_port = int(port or self.config.get("led_controller_port", 5005))
            result = self.bridge.ping(target_ip, target_port)
        self._record_operation(
            "LED 屏",
            "测试连接",
            target=f"{target_ip}:{target_port}",
            result="success" if result.ok else "fail",
            detail=result.message,
        )
        return result

    def _controller_target(self):
        return "{}:{}".format(
            self.config.get("led_controller_ip", "192.168.100.1"),
            int(self.config.get("led_controller_port", 5005)),
        )

    def _record_operation(
        self,
        category,
        action,
        target="",
        result="",
        detail="",
    ):
        if not self.operation_logger:
            return
        try:
            self.operation_logger.record(
                category=category,
                action=action,
                target=target,
                result=result,
                detail=detail,
                source="本机",
            )
        except Exception as exc:
            print(f"[Log] Operation Log Write Error: {exc}")

    def clear_async(self, ip=None, port=None):
        target_ip = ip or self.config.get("led_controller_ip", "192.168.100.1")
        target_port = int(port or self.config.get("led_controller_port", 5005))

        def clear():
            try:
                self._stop_display_session()
                with self._operation_lock:
                    result = self.bridge.clear(target_ip, target_port)
                self._log_failed_result("清屏", result)
            except Exception as exc:
                print(f"[LED] Clear error: {exc}")
                result = BridgeResult(False, str(exc))
            self._record_operation(
                "LED 屏",
                "清除当前画面",
                target=f"{target_ip}:{target_port}",
                result="success" if result.ok else "fail",
                detail=result.message,
            )
            return result

        return self._submitter(clear)

    def reset_and_restore(self, ip=None, port=None):
        self.reset_statuses()
        _, generation = self._stop_display_session()
        target_ip = ip or self.config.get("led_controller_ip", "192.168.100.1")
        target_port = int(port or self.config.get("led_controller_port", 5005))
        with self._operation_lock:
            with self._lock:
                superseded = generation != self._display_generation
            if superseded:
                result = BridgeResult(True, "恢复请求已被新的显示状态取代")
            else:
                result = self.bridge.clear(target_ip, target_port)
        if result.ok:
            result = BridgeResult(True, "已清空班级状态并恢复控制卡原节目")
        self._record_operation(
            "LED 屏",
            "清空状态并恢复原节目",
            target=f"{target_ip}:{target_port}",
            result="success" if result.ok else "fail",
            detail=result.message,
        )
        return result

    def reset_and_restore_async(self, ip=None, port=None, clear_statuses=True):
        def restore():
            if clear_statuses:
                return self.reset_and_restore(ip, port)
            self._stop_display_session()
            target_ip = ip or self.config.get("led_controller_ip", "192.168.100.1")
            target_port = int(port or self.config.get("led_controller_port", 5005))
            with self._operation_lock:
                result = self.bridge.clear(target_ip, target_port)
            if result.ok:
                return BridgeResult(True, "已恢复控制卡原节目")
            return result

        return self._submitter(restore)

    def send_test_screen(
        self,
        ip=None,
        port=None,
        title=None,
        stay_seconds=None,
        grades_per_page=None,
    ):
        self.reset_statuses()
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

        with self._page_files_lock:
            pages = render_led_pages(
                title or self.config.get("led_school_title", "数智家校\n放学系统"),
                classes,
                statuses,
                self.output_dir,
                width=int(self.config.get("led_width", 1024)),
                height=int(self.config.get("led_height", 96)),
                grades_per_page=int(
                    grades_per_page
                    if grades_per_page is not None
                    else self.config.get("led_grades_per_page", 2)
                ),
            )
            result = self._start_display_session(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                float(stay_seconds or self.config.get("led_page_seconds", 5)),
            )
        self._record_operation(
            "LED 屏",
            "发送测试画面",
            target="{}:{}".format(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
            ),
            result="success" if result.ok else "fail",
            detail=result.message,
        )
        return result

    def _start_display_session(
        self,
        ip,
        port,
        pages,
        stay_seconds,
        require_dismissal_active=False,
    ):
        pages = list(pages)
        if not pages:
            return BridgeResult(False, "没有可发送的 LED 页面")
        with self._lock:
            if require_dismissal_active and not self._dismissal_active:
                return BridgeResult(True, "放学时段已结束，未发送 LED 页面")
            self._cancel_display_timer_locked()
            self._display_generation += 1
            generation = self._display_generation
            self._display_pages = pages
            self._display_index = 0
            self._display_target = (ip, int(port))
            self._display_interval = max(1.0, float(stay_seconds))
            first_page = pages[0]
        with self._operation_lock:
            with self._lock:
                superseded = (
                    generation != self._display_generation
                    or (
                        require_dismissal_active
                        and not self._dismissal_active
                    )
                )
                interval = self._display_interval
            if superseded:
                return BridgeResult(True, "显示请求已被新的操作取代")
            result = self.bridge.display(
                ip,
                int(port),
                [first_page],
                stay_seconds=interval,
            )
        if result.ok:
            self._schedule_display_rotation(generation)
            if len(pages) > 1:
                return BridgeResult(
                    True,
                    f"已启动 {len(pages)} 个 LED 页面轮播，每页 {self._display_interval:g} 秒",
                )
        return result

    def _schedule_display_rotation(self, generation):
        with self._lock:
            if (
                generation != self._display_generation
                or len(self._display_pages) <= 1
                or self._shutdown_event.is_set()
            ):
                return
            timer = self._make_timer(
                self._display_interval,
                lambda: self._queue_display_rotation(generation, timer),
            )
            self._display_timer = timer
            timer.start()

    def _queue_display_rotation(self, generation, timer):
        with self._lock:
            if (
                generation != self._display_generation
                or self._display_timer is not timer
                or self._shutdown_event.is_set()
            ):
                return
            self._display_timer = None
        try:
            self._submitter(lambda: self._run_display_rotation(generation))
        except Exception as exc:
            print(f"[LED] Failed to queue page rotation: {exc}")

    def _run_display_rotation(self, generation):
        with self._lock:
            if (
                generation != self._display_generation
                or len(self._display_pages) <= 1
                or self._shutdown_event.is_set()
            ):
                return None
            self._display_index = (self._display_index + 1) % len(self._display_pages)
            page = self._display_pages[self._display_index]
            ip, port = self._display_target
            interval = self._display_interval
        with self._page_files_lock:
            with self._operation_lock:
                with self._lock:
                    superseded = generation != self._display_generation
                if superseded:
                    return BridgeResult(True, "翻页请求已被新的操作取代")
                result = self.bridge.display(ip, port, [page], stay_seconds=interval)
        if not result.ok:
            self._log_failed_result("翻页", result)
        self._schedule_display_rotation(generation)
        return result

    def _stop_display_session(self):
        with self._lock:
            had_session = bool(self._display_pages)
            self._cancel_display_timer_locked()
            self._display_generation += 1
            self._display_pages = []
            self._display_target = None
            return had_session, self._display_generation

    def _cancel_display_timer_locked(self):
        timer = self._display_timer
        self._display_timer = None
        if timer is not None:
            timer.cancel()

    def _cancel_status_timer_locked(self, class_id):
        timer = self._status_timers.pop(class_id, None)
        if timer is not None:
            timer.cancel()

    def _cancel_all_status_timers_locked(self):
        timers = list(self._status_timers.values())
        self._status_timers.clear()
        for timer in timers:
            timer.cancel()

    def _make_timer(self, delay, callback):
        timer = self._timer_factory(delay, callback)
        if hasattr(timer, "daemon"):
            timer.daemon = True
        return timer

    def _make_status_timer(self, delay, class_id):
        timer = None

        def complete():
            self._complete_dismissal(class_id, timer)

        timer = self._make_timer(delay, complete)
        return timer

    def shutdown(self):
        self._shutdown_event.set()
        self._stop_display_session()
        with self._lock:
            self._cancel_all_status_timers_locked()
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
