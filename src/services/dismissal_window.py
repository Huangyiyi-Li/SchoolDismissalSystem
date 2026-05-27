from __future__ import annotations

import datetime as dt

from .class_types import format_class_type_section_title, normalize_class_type
from .schedule_display import is_usable_range


_WEEKDAY_NAMES = {
    1: "星期一",
    2: "星期二",
    3: "星期三",
    4: "星期四",
    5: "星期五",
    6: "星期六",
    7: "星期日",
}


def _parse_clock(value: str) -> dt.time:
    return dt.datetime.strptime(value, "%H:%M").time()


def _iter_schedule_rules(schedules, class_type=None):
    for item in schedules or []:
        if "schedules" in item:
            item_class_type = normalize_class_type(item.get("classType"))
            if class_type is not None and item_class_type != class_type:
                continue
            for rule in item.get("schedules") or []:
                yield rule
        else:
            yield item


def _is_usable_range(time_range):
    return is_usable_range(time_range)


def get_active_window_signature(
    schedules,
    fallback_start,
    fallback_end,
    now=None,
    class_type=None,
):
    now = now or dt.datetime.now()
    current_weekday = now.weekday() + 1
    current_time = now.time()
    has_schedule = bool(schedules)

    for rule in _iter_schedule_rules(schedules, class_type=class_type):
        if rule.get("weekday") != current_weekday:
            continue
        for time_range in rule.get("timeRanges") or []:
            if not _is_usable_range(time_range):
                continue
            start_str = time_range.get("startTime")
            end_str = time_range.get("endTime")
            if not start_str or not end_str:
                continue
            start = _parse_clock(start_str)
            end = _parse_clock(end_str)
            if start <= current_time <= end:
                return f"dynamic:{current_weekday}:{start_str}-{end_str}"

    if has_schedule:
        return None

    start = _parse_clock(fallback_start)
    end = _parse_clock(fallback_end)
    if start <= current_time <= end:
        return f"static:{fallback_start}-{fallback_end}"
    return None


def is_now_within_window(schedules, fallback_start, fallback_end, now=None, class_type=None):
    return (
        get_active_window_signature(
            schedules,
            fallback_start,
            fallback_end,
            now=now,
            class_type=class_type,
        )
        is not None
    )


def format_window_label(schedules, fallback_start, fallback_end, now=None, class_type=None):
    now = now or dt.datetime.now()
    current_weekday = now.weekday() + 1
    today_ranges = []
    for rule in _iter_schedule_rules(schedules, class_type=class_type):
        if rule.get("weekday") != current_weekday:
            continue
        for time_range in rule.get("timeRanges") or []:
            if not _is_usable_range(time_range):
                continue
            start = time_range.get("startTime")
            end = time_range.get("endTime")
            if start and end:
                label = f"{start}-{end}"
                if label not in today_ranges:
                    today_ranges.append(label)
    if today_ranges:
        date_label = f"{now.year} 年 {now.month} 月 {now.day} 日 {_WEEKDAY_NAMES[current_weekday]}"
        return "\n".join([date_label, *today_ranges])
    return f"默认: {fallback_start} - {fallback_end}"


def format_grouped_window_label(schedules, fallback_start, fallback_end, now=None):
    now = now or dt.datetime.now()
    current_weekday = now.weekday() + 1
    date_label = f"{now.year} 年 {now.month} 月 {now.day} 日 {_WEEKDAY_NAMES[current_weekday]}"
    sections = [date_label]

    for class_type in (1, 2):
        section_lines = [format_class_type_section_title(class_type)]
        ranges = []
        for rule in _iter_schedule_rules(schedules, class_type=class_type):
            if rule.get("weekday") != current_weekday:
                continue
            for time_range in rule.get("timeRanges") or []:
                if not _is_usable_range(time_range):
                    continue
                start = time_range.get("startTime")
                end = time_range.get("endTime")
                if start and end:
                    label = f"{start}-{end}"
                    if label not in ranges:
                        ranges.append(label)
        section_lines.extend(ranges or ["未配置"])
        sections.append("\n".join(section_lines))

    if not schedules:
        sections = [
            date_label,
            "\n".join(
                [
                    format_class_type_section_title(1),
                    f"默认: {fallback_start} - {fallback_end}",
                ]
            ),
            "\n".join([format_class_type_section_title(2), "未配置"]),
        ]

    return "\n\n".join(sections)
