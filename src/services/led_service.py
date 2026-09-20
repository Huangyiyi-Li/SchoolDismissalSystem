import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .led_bridge_client import BridgeResult, JavaLedBridge
from .led_renderer import render_club_led_pages, render_led_pages
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
        self._test_statuses = {}
        self._test_mode = False
        self._status_timers = {}
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._page_files_lock = threading.Lock()
        self._schedule_lock = threading.Lock()
        self._timer_factory = timer_factory or threading.Timer
        self.operation_logger = operation_logger
        self._dismissal_active = bool(dismissal_active)
        self._dismissal_state_initialized = dismissal_active is not None
        self._active_class_types = {1} if dismissal_active else set()
        self._display_timer = None
        self._display_generation = 0
        self._display_pages = []
        self._display_index = 0
        self._display_target = None
        self._display_dimensions = (1024, 96)
        self._display_color_mode = "single"
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

    @staticmethod
    def _status_key(class_id, class_type=1):
        return (int(class_type or 1), str(class_id or "").strip())

    @staticmethod
    def _normalize_visible_grades(values):
        if not isinstance(values, (list, tuple, set)):
            return []
        normalized = []
        for value in values:
            grade_name = str(value or "").strip()
            if grade_name and grade_name not in normalized:
                normalized.append(grade_name)
        return normalized

    def get_available_admin_grades(self, school_id=None):
        school_id = school_id or self.config.get("school_id")
        grades = []
        for item in self.db.get_led_classes(school_id, class_type=1):
            grade_name = str(item.get("grade_name") or "").strip()
            if grade_name and grade_name not in grades:
                grades.append(grade_name)
        return grades

    def _filter_classes_by_grades(
        self,
        classes_by_type,
        grade_filter_mode=None,
        visible_grades=None,
    ):
        mode = (
            grade_filter_mode
            if grade_filter_mode is not None
            else self.config.get("led_grade_filter_mode", "all")
        )
        if mode != "selected":
            return classes_by_type
        configured_grades = (
            visible_grades
            if visible_grades is not None
            else self.config.get("led_visible_grades", [])
        )
        selected = set(self._normalize_visible_grades(configured_grades))
        filtered = dict(classes_by_type)
        filtered[1] = [
            item
            for item in (classes_by_type.get(1) or [])
            if str(item.get("grade_name") or "").strip() in selected
        ]
        return filtered

    def _class_status_affects_led(self, class_id, class_type):
        class_type = int(class_type or 1)
        if class_type != 1:
            return True
        if self.config.get("led_grade_filter_mode", "all") != "selected":
            return True
        selected = set(
            self._normalize_visible_grades(
                self.config.get("led_visible_grades", [])
            )
        )
        class_id = str(class_id or "").strip()
        for item in self.db.get_led_classes(self._school_id(), class_type=1):
            if str(item.get("class_id") or "").strip() == class_id:
                return str(item.get("grade_name") or "").strip() in selected
        return False

    def _active_statuses_locked(self):
        return self._test_statuses if self._test_mode else self._statuses

    def _persist_status_locked(
        self,
        class_id,
        status,
        dismiss_due_at=None,
        class_type=1,
    ):
        school_id = self._school_id()
        if not school_id:
            return
        self.db.save_led_class_status(
            school_id,
            class_id,
            self._status_date.isoformat(),
            status,
            dismiss_due_at.isoformat() if dismiss_due_at else None,
            class_type=class_type,
        )

    def _clear_persisted_statuses_locked(self, school_id=None):
        school_id = str(school_id or self._school_id()).strip()
        if school_id:
            self.db.clear_led_class_statuses(school_id)

    def _clear_class_type_statuses_locked(self, class_type):
        class_type = int(class_type)
        for timer_key in list(self._status_timers):
            if timer_key[1] == class_type:
                self._cancel_status_timer_locked(timer_key)
        for statuses in (self._statuses, self._test_statuses):
            for key in [key for key in statuses if key[0] == class_type]:
                statuses.pop(key, None)
        school_id = self._school_id()
        if school_id:
            self.db.clear_led_class_statuses(
                school_id,
                status_date=self._status_date.isoformat(),
                class_type=class_type,
            )

    def _delete_persisted_status_locked(self, class_id, class_type=1):
        school_id = self._school_id()
        if school_id:
            self.db.delete_led_class_status(
                school_id,
                class_id,
                self._status_date.isoformat(),
                class_type=class_type,
            )

    def _restore_persisted_statuses(self):
        school_id = self._school_id()
        if not school_id:
            return
        now = self.clock()
        rows = self.db.get_led_class_statuses(school_id, now.date().isoformat())
        with self._lock:
            for row in rows:
                class_type = int(row.get("class_type") or 1)
                class_id = str(row.get("class_id") or "").strip()
                key = self._status_key(class_id, class_type)
                status = row.get("status")
                if not class_id or status not in (
                    self.STATUS_DISMISSING,
                    self.STATUS_DISMISSED,
                ):
                    continue
                due_raw = row.get("dismiss_due_at")
                if status == self.STATUS_DISMISSING:
                    if not due_raw:
                        self._statuses[key] = self.STATUS_DISMISSED
                        self._persist_status_locked(
                            class_id,
                            self.STATUS_DISMISSED,
                            class_type=class_type,
                        )
                        continue
                    try:
                        due_at = datetime.datetime.fromisoformat(due_raw)
                    except (TypeError, ValueError):
                        due_at = now
                    remaining = (due_at - now).total_seconds()
                    if remaining <= 0:
                        self._statuses[key] = self.STATUS_DISMISSED
                        self._persist_status_locked(
                            class_id,
                            self.STATUS_DISMISSED,
                            class_type=class_type,
                        )
                        continue
                    self._statuses[key] = status
                    timer_key = (False, *key)
                    timer = self._make_status_timer(remaining, key, False)
                    self._status_timers[timer_key] = timer
                    timer.start()
                else:
                    self._statuses[key] = status

    def _reset_if_new_day(self):
        today = self.clock().date()
        if today != self._status_date:
            self._cancel_all_status_timers_locked()
            self._statuses.clear()
            self._test_statuses.clear()
            self._clear_persisted_statuses_locked()
            self._status_date = today

    def get_status(self, class_id, class_type=1, test_mode=None):
        with self._lock:
            self._reset_if_new_day()
            statuses = (
                self._test_statuses
                if (self._test_mode if test_mode is None else bool(test_mode))
                else self._statuses
            )
            return statuses.get(self._status_key(class_id, class_type), "")

    def display_snapshot(self):
        """Thread-safe shared state for local displays, independent of LED output."""
        with self._lock:
            self._reset_if_new_day()
            return {
                'active': self._dismissal_state_initialized and self._dismissal_active,
                'session': self._window_restore_epoch,
                'class_types': tuple(sorted(self._active_class_types)),
                'statuses': dict(self._active_statuses_locked()),
            }

    def get_statuses_snapshot(self, test_mode=None):
        with self._lock:
            self._reset_if_new_day()
            statuses = (
                self._test_statuses
                if (self._test_mode if test_mode is None else bool(test_mode))
                else self._statuses
            )
            return dict(statuses)

    def mark_dismissing(self, class_id, class_type=1):
        class_id = str(class_id or "").strip()
        class_type = int(class_type or 1)
        key = self._status_key(class_id, class_type)
        if not class_id:
            return False
        with self._lock:
            self._reset_if_new_day()
            if (
                not self._dismissal_active
                or (not self._test_mode and class_type not in self._active_class_types)
            ):
                return False
            statuses = self._active_statuses_locked()
            timer_key = (self._test_mode, *key)
            self._cancel_status_timer_locked(timer_key)
            changed = statuses.get(key, "") != self.STATUS_DISMISSING
            statuses[key] = self.STATUS_DISMISSING
            delay = float(self.config.get("led_dismissed_delay_seconds", 5))
            dismiss_due_at = self.clock() + datetime.timedelta(seconds=delay)
            if not self._test_mode:
                self._persist_status_locked(
                    class_id,
                    self.STATUS_DISMISSING,
                    dismiss_due_at,
                    class_type=class_type,
                )
            timer = self._make_status_timer(delay, key, self._test_mode)
            self._status_timers[timer_key] = timer
            timer.start()
        if changed and self._class_status_affects_led(class_id, class_type):
            self.refresh_async()
        return True

    def mark_dismissed(self, class_id, class_type=1):
        class_id = str(class_id or "").strip()
        if not class_id:
            return False
        with self._lock:
            self._cancel_status_timer_locked(
                (self._test_mode, *self._status_key(class_id, class_type))
            )
        self.set_class_status(class_id, self.STATUS_DISMISSED, class_type=class_type)
        return True

    def _complete_dismissal(self, key, timer, test_mode):
        timer_key = (test_mode, *key)
        with self._lock:
            if (
                self._status_timers.get(timer_key) is not timer
                or (
                    not self._dismissal_active
                    and self._dismissal_state_initialized
                )
                or self._shutdown_event.is_set()
            ):
                return
            self._status_timers.pop(timer_key, None)
            statuses = self._test_statuses if test_mode else self._statuses
            if statuses.get(key) != self.STATUS_DISMISSING:
                return
            statuses[key] = self.STATUS_DISMISSED
            if not test_mode:
                self._persist_status_locked(
                    key[1], self.STATUS_DISMISSED, class_type=key[0]
                )
        if self._test_mode == test_mode and self._class_status_affects_led(
            key[1], key[0]
        ):
            self.refresh_async()

    def set_class_status(self, class_id, status, class_type=1):
        class_id = str(class_id or "").strip()
        class_type = int(class_type or 1)
        key = self._status_key(class_id, class_type)
        if not class_id:
            return
        if status not in ("", self.STATUS_DISMISSING, self.STATUS_DISMISSED):
            raise ValueError(f"不支持的 LED 班级状态: {status}")
        if status == self.STATUS_DISMISSING:
            return self.mark_dismissing(class_id, class_type=class_type)
        with self._lock:
            self._reset_if_new_day()
            statuses = self._active_statuses_locked()
            if statuses.get(key, "") == status:
                return
            if status:
                statuses[key] = status
                if not self._test_mode:
                    self._persist_status_locked(class_id, status, class_type=class_type)
            else:
                statuses.pop(key, None)
                if not self._test_mode:
                    self._delete_persisted_status_locked(class_id, class_type=class_type)
        if self._class_status_affects_led(class_id, class_type):
            self.refresh_async()

    def set_test_mode(self, enabled):
        enabled = bool(enabled)
        with self._lock:
            if self._test_mode == enabled:
                return False
            for timer_key in list(self._status_timers):
                if timer_key[0]:
                    self._cancel_status_timer_locked(timer_key)
            self._test_statuses.clear()
            self._test_mode = enabled
        self.refresh_async()
        return True

    def reset_statuses(self, school_id=None):
        with self._lock:
            self._cancel_all_status_timers_locked()
            self._statuses.clear()
            self._test_statuses.clear()
            self._clear_persisted_statuses_locked(school_id=school_id)
            self._status_date = self.clock().date()

    def set_dismissal_active(self, active, class_types=None):
        active = bool(active)
        requested_types = {
            int(value) for value in (class_types or ({1} if active else set()))
        }
        should_retry_refresh = False
        types_changed = False
        with self._lock:
            previous_types = set(self._active_class_types)
            types_changed = active and requested_types != self._active_class_types
            if active:
                self._active_class_types = requested_types
                for removed_type in previous_types - requested_types:
                    self._clear_class_type_statuses_locked(removed_type)
            else:
                self._active_class_types = set()
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
                if not should_retry_refresh and not types_changed:
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
            if not should_retry_refresh and not types_changed:
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
        with self._lock:
            active_types = sorted(self._active_class_types or {1})
            self._reset_if_new_day()
            statuses = dict(self._active_statuses_locked())
        classes_by_type = {
            class_type: self.db.get_led_classes(school_id, class_type=class_type)
            for class_type in active_types
        }
        classes_by_type = self._filter_classes_by_grades(classes_by_type)
        if not any(classes_by_type.values()):
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

        width = int(self.config.get("led_width", 1024))
        height = int(self.config.get("led_height", 96))
        color_mode = self.config.get("led_color_mode", "single")
        with self._page_files_lock:
            pages = self._render_pages_for_types(
                classes_by_type,
                statuses,
                self.output_dir,
                title=title,
                width=width,
                height=height,
                color_mode=color_mode,
            )
            result = self._start_display_session(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                float(stay_seconds or self.config.get("led_page_seconds", 5)),
                require_dismissal_active=True,
                width=width,
                height=height,
                color_mode=color_mode,
            )
        if not result.ok:
            print(f"[LED] Push failed: {result.message}")
        return result

    def _render_pages_for_types(
        self,
        classes_by_type,
        statuses,
        output_dir,
        title=None,
        width=None,
        height=None,
        grades_per_page=None,
        regions_per_page=None,
        show_title=None,
        club_rows_per_group=None,
        club_groups_per_page=None,
        color_mode=None,
        title_font_size=None,
        header_font_size=None,
        cell_font_size=None,
        grade_filter_mode=None,
        visible_grades=None,
        title_position=None,
        pixel_scale=1.0,
    ):
        width = int(width if width is not None else self.config.get("led_width", 1024))
        height = int(height if height is not None else self.config.get("led_height", 96))
        rows = int(
            grades_per_page
            if grades_per_page is not None
            else self.config.get("led_grades_per_page", 2)
        )
        regions = int(
            regions_per_page
            if regions_per_page is not None
            else self.config.get("led_layout_regions", 1)
        )
        club_rows = int(
            club_rows_per_group
            if club_rows_per_group is not None
            else self.config.get("led_club_rows_per_group", 4)
        )
        club_groups = int(
            club_groups_per_page
            if club_groups_per_page is not None
            else self.config.get("led_club_groups_per_page", 5)
        )
        display_title = (
            self.config.get("led_school_title", "数智家校\n放学系统")
            if title is None
            else title
        )
        title_visible = (
            bool(self.config.get("led_show_title", True))
            if show_title is None
            else bool(show_title)
        )
        active_color_mode = (
            color_mode
            if color_mode is not None
            else self.config.get("led_color_mode", "single")
        )
        active_title_font_size = int(
            title_font_size
            if title_font_size is not None
            else self.config.get("led_title_font_size", 0)
        )
        active_header_font_size = int(
            header_font_size
            if header_font_size is not None
            else self.config.get("led_header_font_size", 0)
        )
        active_cell_font_size = int(
            cell_font_size
            if cell_font_size is not None
            else self.config.get("led_cell_font_size", 0)
        )
        classes_by_type = self._filter_classes_by_grades(
            classes_by_type,
            grade_filter_mode=grade_filter_mode,
            visible_grades=visible_grades,
        )
        pages = []
        for class_type in (1, 2):
            classes = classes_by_type.get(class_type) or []
            if not classes:
                continue
            if class_type == 2:
                rendered = render_club_led_pages(
                    display_title,
                    classes,
                    statuses,
                    output_dir,
                    width=width,
                    height=height,
                    rows_per_group=club_rows,
                    groups_per_page=club_groups,
                    show_title=title_visible,
                    title_position=title_position or self.config.get("led_title_position", "left"),
                    pixel_scale=pixel_scale,
                    filename_prefix="led-club-page",
                    color_mode=active_color_mode,
                    title_font_size=active_title_font_size,
                    header_font_size=active_header_font_size,
                    cell_font_size=active_cell_font_size,
                )
            else:
                rendered = render_led_pages(
                    display_title,
                    classes,
                    statuses,
                    output_dir,
                    width=width,
                    height=height,
                    grades_per_page=rows,
                    regions_per_page=regions,
                    show_title=title_visible,
                    title_position=title_position or self.config.get("led_title_position", "left"),
                    pixel_scale=pixel_scale,
                    class_type=1,
                    filename_prefix="led-page",
                    color_mode=active_color_mode,
                    title_font_size=active_title_font_size,
                    header_font_size=active_header_font_size,
                    cell_font_size=active_cell_font_size,
                )
            pages.extend(rendered)
        return pages

    def render_preview_pages(
        self,
        output_dir,
        width,
        height,
        grades_per_page,
        regions_per_page,
        show_title,
        title,
        sample_statuses=False,
        club_rows_per_group=None,
        club_groups_per_page=None,
        color_mode=None,
        title_font_size=None,
        header_font_size=None,
        cell_font_size=None,
        grade_filter_mode=None,
        visible_grades=None,
        title_position=None,
        pixel_scale=1.0,
    ):
        school_id = self.config.get("school_id")
        classes_by_type = {
            class_type: self.db.get_led_classes(school_id, class_type=class_type)
            for class_type in (1, 2)
        }
        statuses = self.get_statuses_snapshot()
        if sample_statuses:
            statuses = {}
            index = 0
            for class_type in (1, 2):
                for item in classes_by_type[class_type]:
                    sample = (
                        self.STATUS_DISMISSING,
                        self.STATUS_DISMISSED,
                        "",
                    )[index % 3]
                    if sample:
                        statuses[self._status_key(item.get("class_id"), class_type)] = sample
                    index += 1
        with self._page_files_lock:
            return self._render_pages_for_types(
                classes_by_type,
                statuses,
                output_dir,
                title=title,
                width=width,
                height=height,
                grades_per_page=grades_per_page,
                regions_per_page=regions_per_page,
                show_title=show_title,
                club_rows_per_group=club_rows_per_group,
                club_groups_per_page=club_groups_per_page,
                color_mode=color_mode,
                title_font_size=title_font_size,
                header_font_size=header_font_size,
                cell_font_size=cell_font_size,
                grade_filter_mode=grade_filter_mode,
                visible_grades=visible_grades,
                title_position=title_position,
                pixel_scale=pixel_scale,
            )

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
        regions_per_page=None,
        show_title=None,
        width=None,
        height=None,
        club_rows_per_group=None,
        club_groups_per_page=None,
        color_mode=None,
        title_font_size=None,
        header_font_size=None,
        cell_font_size=None,
        grade_filter_mode=None,
        visible_grades=None,
        title_position=None,
        pixel_scale=1.0,
    ):
        school_id = self.config.get("school_id")
        classes_by_type = {
            class_type: self.db.get_led_classes(school_id, class_type=class_type)
            for class_type in (1, 2)
        }
        effective_filter_mode = (
            grade_filter_mode
            if grade_filter_mode is not None
            else self.config.get("led_grade_filter_mode", "all")
        )
        effective_visible_grades = self._normalize_visible_grades(
            visible_grades
            if visible_grades is not None
            else self.config.get("led_visible_grades", [])
        )
        filtered_classes = self._filter_classes_by_grades(
            classes_by_type,
            grade_filter_mode=effective_filter_mode,
            visible_grades=effective_visible_grades,
        )
        fallback_grades = []
        if (
            effective_filter_mode == "selected"
            and effective_visible_grades
            and not filtered_classes.get(1)
        ):
            fallback_grades = effective_visible_grades
        elif not any(classes_by_type.values()):
            fallback_grades = ["测试"]
        if fallback_grades:
            fallback_count = max(3, len(fallback_grades))
            classes_by_type[1] = [
                {
                    "class_id": f"LED-TEST-{index}",
                    "class_type": 1,
                    "grade_name": fallback_grades[
                        (index - 1) % len(fallback_grades)
                    ],
                    "class_name": f"测试{index}班",
                    "class_show_name": f"{index}班",
                    "source_order": index - 1,
                }
                for index in range(1, fallback_count + 1)
            ]
        statuses = {}
        index = 0
        for class_type in (1, 2):
            for item in classes_by_type[class_type]:
                sample = (
                    self.STATUS_DISMISSING,
                    self.STATUS_DISMISSED,
                    "",
                )[index % 3]
                if sample:
                    statuses[self._status_key(item.get("class_id"), class_type)] = sample
                index += 1

        width = int(width if width is not None else self.config.get("led_width", 1024))
        height = int(height if height is not None else self.config.get("led_height", 96))
        active_color_mode = (
            color_mode
            if color_mode is not None
            else self.config.get("led_color_mode", "single")
        )

        with self._page_files_lock:
            pages = self._render_pages_for_types(
                classes_by_type,
                statuses,
                self.output_dir,
                title=title,
                width=width,
                height=height,
                grades_per_page=grades_per_page,
                regions_per_page=regions_per_page,
                show_title=show_title,
                club_rows_per_group=club_rows_per_group,
                club_groups_per_page=club_groups_per_page,
                color_mode=active_color_mode,
                title_font_size=title_font_size,
                header_font_size=header_font_size,
                cell_font_size=cell_font_size,
                grade_filter_mode=grade_filter_mode,
                visible_grades=visible_grades,
                title_position=title_position,
                pixel_scale=pixel_scale,
            )
            result = self._start_display_session(
                ip or self.config.get("led_controller_ip", "192.168.100.1"),
                int(port or self.config.get("led_controller_port", 5005)),
                pages,
                float(stay_seconds or self.config.get("led_page_seconds", 5)),
                width=width,
                height=height,
                color_mode=active_color_mode,
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
        width=1024,
        height=96,
        color_mode="single",
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
            self._display_dimensions = (int(width), int(height))
            self._display_color_mode = color_mode
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
                width=int(width),
                height=int(height),
                color_mode=color_mode,
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
            width, height = self._display_dimensions
            interval = self._display_interval
            color_mode = self._display_color_mode
        with self._page_files_lock:
            with self._operation_lock:
                with self._lock:
                    superseded = generation != self._display_generation
                if superseded:
                    return BridgeResult(True, "翻页请求已被新的操作取代")
                result = self.bridge.display(
                    ip,
                    port,
                    [page],
                    stay_seconds=interval,
                    width=width,
                    height=height,
                    color_mode=color_mode,
                )
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

    def _cancel_status_timer_locked(self, timer_key):
        timer = self._status_timers.pop(timer_key, None)
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

    def _make_status_timer(self, delay, key, test_mode):
        timer = None

        def complete():
            self._complete_dismissal(key, timer, test_mode)

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


class _ScreenOutput(LedService):
    """One output queue and rotation; never owns or persists dismissal events."""
    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        self.last_result = None
        self._manual_restore_pending = False
        self._manual_restore_in_flight = False
        super().__init__(*args, **kwargs)
        self._requested_config = self.config

    def _restore_persisted_statuses(self):
        pass

    def reset_statuses(self, school_id=None):
        pass

    def _clear_class_type_statuses_locked(self, class_type):
        pass

    def get_statuses_snapshot(self, test_mode=None):
        return self.owner.get_statuses_snapshot(test_mode)

    def refresh(self, *args, **kwargs):
        if self._shutdown_event.is_set() or not self.config.get("led_enabled", False):
            return BridgeResult(True, "此屏未启用，未发送画面")
        self._manual_restore_pending = False
        snapshot = self.owner.get_statuses_snapshot()
        with self._lock:
            self._status_date = self.clock().date()
            self._statuses = snapshot
            self._test_mode = False
        result = super().refresh(*args, **kwargs)
        self.last_result = result
        return result

    def _record_operation(self, category, action, target="", result="", detail=""):
        if result in ("success", "fail"):
            self.last_result = BridgeResult(result == "success", detail)
        return super()._record_operation(category, action, target, result, detail)

    def restore_original_async(self):
        with self._lock:
            if self._manual_restore_in_flight:
                return BridgeResult(False, "该屏正在恢复原节目，请稍后查看状态")
            self._manual_restore_in_flight = True
            self._manual_restore_pending = False
        _, generation = self._stop_display_session()

        def restore():
            try:
                with self._operation_lock:
                    with self._lock:
                        if generation != self._display_generation:
                            return BridgeResult(True, "恢复请求已被新的画面取代")
                    result = self.bridge.clear(self.config.get('led_controller_ip'), self.config.get('led_controller_port'))
            except Exception as exc:
                result = BridgeResult(False, str(exc))
            finally:
                with self._lock:
                    self._manual_restore_in_flight = False
            with self._lock:
                self._manual_restore_pending = not result.ok and generation == self._display_generation
            self._record_operation("LED 屏", "恢复此屏原节目", self._controller_target(),
                                   "success" if result.ok else "fail", result.message)
            return result
        return self._submitter(restore)

    def retry_manual_restore(self):
        if self._manual_restore_pending:
            self.restore_original_async()

    def _run_display_rotation(self, generation):
        try:
            result = super()._run_display_rotation(generation)
        except Exception as exc:
            result = BridgeResult(False, str(exc))
        if result is not None:
            self.last_result = result
            if not result.ok:
                with self._lock:
                    self._window_refresh_pending = True
                    self._next_window_refresh_retry_at = None
        return result

    def _run_refresh_once(self):
        result = super()._run_refresh_once()
        if result is not None:
            self.last_result = result
        return result


class MultiScreenLedService(LedService):
    """A single school status owner dispatching to independent screen services."""
    def __init__(self, config_manager, db_manager, bridge_factory=None,
                 output_submitter=None, **kwargs):
        self.outputs = {}
        self._outputs_lock = threading.RLock()
        self._bridge_factory = bridge_factory
        self._output_submitter = output_submitter
        self._aux_outputs = {}
        super().__init__(config_manager, db_manager, **kwargs)
        self.reconfigure(refresh=False)

    def _class_status_affects_led(self, class_id, class_type):
        # Filtering belongs to outputs, never to shared event storage.
        return True

    def _queue_window_restore(self):
        # The owner has no physical screen. Each output restores independently.
        with self._lock:
            self._window_restore_pending = False

    def refresh_async(self):
        if self._shutdown_event.is_set():
            return None
        with self._outputs_lock:
            outputs = list(self.outputs.values())
        for output in outputs:
            output.refresh_async()
        return None

    def set_dismissal_active(self, active, class_types=None):
        # Publish the shared transition before outputs take their next snapshot.
        changed = super().set_dismissal_active(active, class_types)
        with self._lock:
            # Retry ownership belongs to each physical output.
            self._window_refresh_pending = False
            self._next_window_refresh_retry_at = None
        with self._outputs_lock:
            outputs = list(self.outputs.values())
            retired = list(self._aux_outputs.values())
        for output in outputs:
            output.retry_manual_restore()
            output.set_dismissal_active(active and output.config.get('led_enabled', False), class_types)
        for output in retired:
            output.retry_manual_restore()
            output.set_dismissal_active(False)
        return changed

    def reconfigure(self, refresh=True, reset_outputs=False):
        import uuid
        from .config_manager import load_led_setup, validate_led_setup, LedScreenConfig
        screens, plans = load_led_setup(self.config)
        validate_led_setup(screens, plans)
        plans = {plan['id']: plan for plan in plans}
        with self._outputs_lock:
            # A worker belongs to a physical endpoint. Reassigning names or
            # swapping screen addresses must not let an old clear erase a new send.
            pool = list(dict.fromkeys([*self.outputs.values(), *self._aux_outputs.values()]))
            previous = set(self.outputs.values())
            assigned = {}
            for screen in screens:
                if screen.get("settings", {}).get("led_output_type") == "desktop":
                    continue
                effective = LedScreenConfig(self.config, screen, plans[screen['plan_id']])
                output = next((candidate for candidate in pool
                               if all(candidate.config.get(k) == effective.get(k) for k in
                                      ('led_controller_ip', 'led_controller_port'))), None)
                if output is None:
                    output = _ScreenOutput(
                        self, effective, self.db,
                        bridge=self._bridge_factory(screen) if self._bridge_factory else None,
                        output_dir=self.output_dir / (screen['id'] + '-' + uuid.uuid4().hex),
                        submitter=self._output_submitter,
                        clock=self.clock, timer_factory=self._timer_factory,
                        dismissal_active=(self._dismissal_active and effective.get('led_enabled')) if self._dismissal_state_initialized else None,
                        operation_logger=self.operation_logger)
                    output._active_class_types = set(self._active_class_types)
                else:
                    pool.remove(output)
                assigned[screen['id']] = output
                if reset_outputs or output._requested_config is None or output._requested_config.values != effective.values:
                    output._requested_config = effective
                    output._stop_display_session()
                    # Capture the old config at execution, after earlier edits.
                    def apply(output=output, effective=effective):
                        if output._requested_config is not effective:
                            return
                        output._stop_display_session()
                        old = output.config
                        if old.get('led_enabled') and not effective.get('led_enabled'):
                            output.set_dismissal_active(False)
                        elif old.get('led_enabled') and (
                            reset_outputs or old.get('led_color_mode') != effective.get('led_color_mode')
                        ):
                            with output._operation_lock:
                                output.last_result = output.bridge.clear(old.get('led_controller_ip'), old.get('led_controller_port'))
                        output.config = effective
                        if not (old.get('led_enabled') and not effective.get('led_enabled')):
                            output.set_dismissal_active(self._dismissal_active and effective.get('led_enabled'), self._active_class_types)
                        if refresh:
                            output.refresh_async()
                    output._submitter(apply)
            # Retired endpoints retain their queues so an immediate re-add is safe.
            self._aux_outputs = {id(output): output for output in pool}
            for output in pool:
                if output in previous:
                    output._requested_config = None
                    output.set_dismissal_active(False)
                    output.config.values['led_enabled'] = False
            self.outputs = assigned
        if refresh:
            self.refresh_async()

    def _target_output(self, ip=None, port=None):
        with self._outputs_lock:
            for output in [*self.outputs.values(), *self._aux_outputs.values()]:
                if (ip is None or output.config.get('led_controller_ip') == ip) and (
                    port is None or int(output.config.get('led_controller_port')) == int(port)
                ):
                    return output
            # Unsaved screens can be tested without altering saved configuration.
            key = (ip, port)
            if key not in self._aux_outputs:
                from .config_manager import LedScreenConfig
                config = LedScreenConfig(self.config, {'enabled': False, 'settings': {
                    'led_controller_ip': ip, 'led_controller_port': port or 5005}}, {})
                self._aux_outputs[key] = _ScreenOutput(
                    self, config, self.db,
                    bridge=self._bridge_factory({'id': 'draft-' + str(len(self._aux_outputs))}) if self._bridge_factory else None,
                    output_dir=self.output_dir / ('test-' + str(len(self._aux_outputs))),
                    dismissal_active=False, operation_logger=self.operation_logger)
            return self._aux_outputs[key]

    def test_connection(self, ip=None, port=None):
        output = self._target_output(ip, port)
        result = output.test_connection(ip, port)
        output.last_result = result
        return result

    def send_test_screen(self, **kwargs):
        output = self._target_output(kwargs.get('ip'), kwargs.get('port'))
        pending = output._submitter(lambda: output.send_test_screen(**kwargs))
        result = pending.result() if hasattr(pending, "result") else pending
        output.last_result = result
        return result

    def restore_screen(self, screen_id):
        output = self.outputs[screen_id]
        result = output.restore_original_async()
        return result.result() if hasattr(result, 'result') else result

    def restore_target(self, ip=None, port=None):
        output = self._target_output(ip, port)
        result = output.restore_original_async()
        return result.result() if hasattr(result, 'result') else result

    def clear_async(self, ip=None, port=None):
        return self._target_output(ip, port).clear_async(ip, port)

    def reset_and_restore(self, ip=None, port=None):
        self.reset_statuses()
        with self._outputs_lock:
            outputs = list(self.outputs.values())
        pending = [output.restore_original_async() for output in outputs]
        results = [item.result() if hasattr(item, 'result') else item for item in pending]
        return BridgeResult(all(result.ok for result in results), '已重置全校状态并恢复所有屏幕原节目' if all(result.ok for result in results) else '全校状态已重置，部分屏幕恢复失败，请检查连接')

    def screen_statuses(self):
        with self._outputs_lock:
            return {sid: ('未启用 · 最近通信失败' if not output.config.get('led_enabled') and output.last_result is not None and not output.last_result.ok else
                          '未启用' if not output.config.get('led_enabled') else
                          '尚未连接' if output.last_result is None else
                          '最近通信成功' if output.last_result.ok else '通信失败')
                    for sid, output in self.outputs.items()}

    def shutdown(self):
        super().shutdown()
        with self._outputs_lock:
            for output in [*self.outputs.values(), *self._aux_outputs.values()]:
                output.shutdown()
