from __future__ import annotations

import datetime as _dt


def _normalize_now(now: _dt.datetime | None) -> _dt.datetime:
    return now or _dt.datetime.now()


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":", 1)
    if len(parts) != 2:
        return None
    hour_str, minute_str = parts
    try:
        hour = int(hour_str)
        minute = int(minute_str)
    except (TypeError, ValueError):
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _to_minutes(value: str) -> int | None:
    parsed = _parse_hhmm(value)
    if parsed is None:
        return None
    hour, minute = parsed
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
                if _to_minutes(start) is None or _to_minutes(end) is None:
                    continue
                today.append((weekday, start, end))
    return today


def _weekday_ranges(schedules: list[dict] | None, weekday: int) -> list[tuple[int, str, str]]:
    if not schedules:
        return []

    ranges = []
    for schedule in schedules:
        if schedule.get("weekday") != weekday:
            continue
        for item in schedule.get("timeRanges", []):
            start = item.get("startTime")
            end = item.get("endTime")
            if start and end and (start != "00:00" or end != "00:00"):
                if _to_minutes(start) is None or _to_minutes(end) is None:
                    continue
                ranges.append((weekday, start, end))
    return ranges


def _in_static_range(current_minutes: int, start_minutes: int, end_minutes: int) -> bool:
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


def _in_dynamic_today_range(current_minutes: int, start_minutes: int, end_minutes: int) -> bool:
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes


def _in_dynamic_spillover_range(current_minutes: int, start_minutes: int, end_minutes: int) -> bool:
    return start_minutes > end_minutes and current_minutes <= end_minutes


def get_active_window_signature(schedules, fallback_start, fallback_end, now=None):
    current = _normalize_now(now)
    current_minutes = current.hour * 60 + current.minute

    if schedules:
        today_weekday = _current_weekday(current)
        today_ranges = _weekday_ranges(schedules, today_weekday)
        for weekday, start, end in today_ranges:
            start_minutes = _to_minutes(start)
            end_minutes = _to_minutes(end)
            if start_minutes is None or end_minutes is None:
                continue
            if _in_dynamic_today_range(current_minutes, start_minutes, end_minutes):
                return f"dynamic:{weekday}:{start}-{end}"

        previous_weekday = 7 if today_weekday == 1 else today_weekday - 1
        previous_ranges = _weekday_ranges(schedules, previous_weekday)
        for weekday, start, end in previous_ranges:
            start_minutes = _to_minutes(start)
            end_minutes = _to_minutes(end)
            if start_minutes is None or end_minutes is None:
                continue
            if _in_dynamic_spillover_range(current_minutes, start_minutes, end_minutes):
                return f"dynamic:{weekday}:{start}-{end}"

        return None

    start_minutes = _to_minutes(fallback_start)
    end_minutes = _to_minutes(fallback_end)
    if start_minutes is None or end_minutes is None:
        return None
    if _in_static_range(current_minutes, start_minutes, end_minutes):
        return f"static:{fallback_start}-{fallback_end}"

    return None


def is_now_within_window(schedules, fallback_start, fallback_end, now=None):
    return get_active_window_signature(schedules, fallback_start, fallback_end, now=now) is not None


def format_window_label(schedules, fallback_start, fallback_end, now=None):
    current = _normalize_now(now)
    today_ranges = _today_ranges(schedules, current)

    if today_ranges:
        ranges_text = ", ".join(f"{start}-{end}" for _, start, end in today_ranges)
        return f"今日: {ranges_text}"

    if schedules:
        return "今日: 无可用时段"

    return f"默认: {fallback_start} - {fallback_end}"
