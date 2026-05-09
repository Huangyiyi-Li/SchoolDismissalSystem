from __future__ import annotations

import datetime as _dt


class MaintenanceSessionController:
    def __init__(self, pin: str, timeout_seconds: int):
        self._pin = str(pin)
        self._timeout_seconds = max(1, int(timeout_seconds))
        self._deadline: _dt.datetime | None = None

    def _normalize_now(self, now: _dt.datetime | None) -> _dt.datetime:
        if now is None:
            if self._deadline is not None and self._deadline.tzinfo is not None:
                current = _dt.datetime.now(tz=self._deadline.tzinfo)
            else:
                current = _dt.datetime.now()
        else:
            current = now

        if self._deadline is None:
            return current

        # Keep comparison safe across naive/aware datetime inputs.
        deadline_is_aware = self._deadline.tzinfo is not None
        current_is_aware = current.tzinfo is not None
        if deadline_is_aware and not current_is_aware:
            return current.replace(tzinfo=self._deadline.tzinfo)
        if not deadline_is_aware and current_is_aware:
            return current.replace(tzinfo=None)
        return current

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
