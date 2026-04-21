from __future__ import annotations

import datetime as _dt


def _normalize_now(now: _dt.datetime | None) -> _dt.datetime:
    return now or _dt.datetime.now()


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_str, minute_str = value.split(":", 1)
    return int(hour_str), int(minute_str)


def _to_minutes(value: str) -> int:
    hour, minute = _parse_hhmm(value)
    return hour * 60 + minute


def _current_weekday(now: _dt.datetime) -> int:
    return now.weekday() + 1


def _today_ranges(schedules: list[dict] | None, now: _dt.datetime) -> list[tuple[int, str, str]]:
    if not schedules:
        return []

    weekday = _current_weekday(now)
    today = []
    for schedule in schedules:
        if schedule.get("weekday") != weekday:
            continue
        for item in schedule.get("timeRanges", []):
            start = item.get("startTime")
            end = item.get("endTime")
            if start and end and (start != "00:00" or end != "00:00"):
                today.append((weekday, start, end))
    return today


def get_active_window_signature(schedules, fallback_start, fallback_end, now=None):
    current = _normalize_now(now)
    today_ranges = _today_ranges(schedules, current)

    if schedules and not today_ranges:
        return None

    current_minutes = current.hour * 60 + current.minute
    for weekday, start, end in today_ranges:
        if _to_minutes(start) <= current_minutes <= _to_minutes(end):
            return f"dynamic:{weekday}:{start}-{end}"

    if not schedules:
        if _to_minutes(fallback_start) <= current_minutes <= _to_minutes(fallback_end):
            return f"static:{fallback_start}-{fallback_end}"
        return None

    return None


def is_now_within_window(schedules, fallback_start, fallback_end, now=None):
    return get_active_window_signature(schedules, fallback_start, fallback_end, now=now) is not None


def format_window_label(schedules, fallback_start, fallback_end, now=None):
    current = _normalize_now(now)
    today_ranges = _today_ranges(schedules, current)

    if today_ranges:
        ranges_text = ", ".join(f"{start}-{end}" for _, start, end in today_ranges)
        return f"今日: {ranges_text}"

    return f"默认: {fallback_start} - {fallback_end}"
