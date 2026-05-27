from __future__ import annotations

from .class_types import normalize_class_type


def iter_schedule_rules_with_type(schedules):
    for item in schedules or []:
        if "schedules" in item:
            class_type = normalize_class_type(item.get("classType"))
            for rule in item.get("schedules") or []:
                yield class_type, rule
        else:
            yield normalize_class_type(item.get("classType")), item


def is_usable_range(time_range):
    return not (
        time_range.get("startTime") == "00:00"
        and time_range.get("endTime") == "00:00"
    )


def group_schedules_by_weekday_and_type(schedules):
    grouped = {}
    for class_type, rule in iter_schedule_rules_with_type(schedules):
        weekday = rule.get("weekday")
        if weekday is None:
            continue
        weekday_group = grouped.setdefault(weekday, {})
        ranges = weekday_group.setdefault(class_type, [])
        for time_range in rule.get("timeRanges") or []:
            if is_usable_range(time_range):
                ranges.append(time_range)
    return grouped
