from __future__ import annotations

import datetime as _dt


class MaintenanceSessionController:
    def __init__(self, pin: str, timeout_seconds: int):
        self._pin = str(pin)
        self._timeout_seconds = max(1, int(timeout_seconds))
        self._deadline: _dt.datetime | None = None

    def _normalize_now(self, now: _dt.datetime | None) -> _dt.datetime:
        return now or _dt.datetime.now()

    def _is_active_at(self, current: _dt.datetime) -> bool:
        return self._deadline is not None and current <= self._deadline

    def unlock(self, attempt: str, now=None) -> bool:
        current = self._normalize_now(now)
        if str(attempt) != self._pin:
            return False
        self._deadline = current + _dt.timedelta(seconds=self._timeout_seconds)
        return True

    def touch(self, now=None) -> None:
        current = self._normalize_now(now)
        if self._is_active_at(current):
            self._deadline = current + _dt.timedelta(seconds=self._timeout_seconds)

    def is_unlocked(self, now=None) -> bool:
        current = self._normalize_now(now)
        if not self._is_active_at(current):
            self._deadline = None
            return False
        return True

