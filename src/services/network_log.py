from __future__ import annotations

import datetime
import glob
import json
import os

from ..utils.path_utils import get_app_root


class NetworkLogManager:
    def __init__(self, log_dir=None, clock=None, max_text_length=20000):
        self.log_dir = log_dir or os.path.join(get_app_root(), "logs")
        self.clock = clock or self._default_clock
        self.max_text_length = max_text_length

    def _default_clock(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def record(
        self,
        protocol,
        direction,
        target,
        request=None,
        response=None,
        elapsed_ms=None,
        result="",
        error="",
    ):
        timestamp = self.clock()
        entry = {
            "timestamp": timestamp,
            "protocol": protocol,
            "direction": direction,
            "target": target,
            "request": self._json_safe(request),
            "response": self._json_safe(response),
            "elapsed_ms": elapsed_ms,
            "result": result or "",
            "error": str(error) if error else "",
        }
        os.makedirs(self.log_dir, exist_ok=True)
        log_path = os.path.join(self.log_dir, f"network-{timestamp[:10]}.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def get_recent_entries(self, limit=500):
        paths = sorted(
            glob.glob(os.path.join(self.log_dir, "network-*.jsonl")),
            reverse=True,
        )
        entries = []
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(entries) >= limit:
                    return entries
        return entries

    def _json_safe(self, value):
        if isinstance(value, bytes):
            return self._truncate(value.decode("utf-8", errors="replace"))
        if isinstance(value, (str, int, float, bool)) or value is None:
            return self._truncate(value) if isinstance(value, str) else value
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return self._truncate(str(value))

    def _truncate(self, value):
        if len(value) <= self.max_text_length:
            return value
        return value[: self.max_text_length] + "...[truncated]"


default_network_logger = NetworkLogManager()
