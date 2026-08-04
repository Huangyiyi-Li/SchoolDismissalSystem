from __future__ import annotations

import datetime
import glob
import json
import os
import threading
import time

from ..utils.path_utils import get_app_root


class OperationLogManager:
    """Small, bounded JSONL log for low-frequency local operations."""

    def __init__(
        self,
        log_dir=None,
        clock=None,
        max_text_length=2000,
        max_file_bytes=1024 * 1024,
        max_files=7,
        dedup_interval_seconds=10,
    ):
        self.log_dir = log_dir or os.path.join(get_app_root(), "logs")
        self.clock = clock or self._default_clock
        self.max_text_length = max_text_length
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self.dedup_interval_seconds = dedup_interval_seconds
        self._lock = threading.Lock()
        self._last_cleanup_date = None
        self._last_entry_key = None
        self._last_entry_monotonic = 0.0

    def _default_clock(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def record(
        self,
        category,
        action,
        target="",
        result="",
        detail="",
        source="系统",
    ):
        timestamp = self.clock()
        entry = {
            "timestamp": timestamp,
            "source": self._truncate(str(source or "系统")),
            "category": self._truncate(str(category or "本地操作")),
            "action": self._truncate(str(action or "")),
            "target": self._truncate(str(target or "")),
            "result": self._truncate(str(result or "")),
            "detail": self._truncate(str(detail or "")),
        }
        with self._lock:
            entry_key = tuple(entry[key] for key in (
                "source", "category", "action", "target", "result", "detail"
            ))
            now_monotonic = time.monotonic()
            if (
                entry_key == self._last_entry_key
                and now_monotonic - self._last_entry_monotonic
                < self.dedup_interval_seconds
            ):
                return entry
            os.makedirs(self.log_dir, exist_ok=True)
            log_path = self._current_log_path(timestamp[:10])
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._cleanup_old_files(timestamp[:10])
            self._last_entry_key = entry_key
            self._last_entry_monotonic = now_monotonic
        return entry

    def get_recent_entries(self, limit=500):
        paths = sorted(
            glob.glob(os.path.join(self.log_dir, "operation-*.jsonl")),
            reverse=True,
        )
        entries = []
        for log_path in paths:
            try:
                with open(log_path, "r", encoding="utf-8") as handle:
                    lines = handle.readlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(entries) >= limit:
                    return entries
        return entries

    def _current_log_path(self, date_text):
        paths = sorted(
            glob.glob(os.path.join(self.log_dir, f"operation-{date_text}-*.jsonl"))
        )
        if paths and os.path.getsize(paths[-1]) < self.max_file_bytes:
            return paths[-1]
        next_index = len(paths) + 1
        return os.path.join(
            self.log_dir,
            f"operation-{date_text}-{next_index:02d}.jsonl",
        )

    def _cleanup_old_files(self, date_text):
        if self._last_cleanup_date == date_text:
            return
        self._last_cleanup_date = date_text
        paths = sorted(glob.glob(os.path.join(self.log_dir, "operation-*.jsonl")))
        for old_path in paths[:-self.max_files]:
            try:
                os.remove(old_path)
            except OSError:
                pass

    def _truncate(self, value):
        if len(value) <= self.max_text_length:
            return value
        return value[: self.max_text_length] + "...[truncated]"


default_operation_logger = OperationLogManager()
