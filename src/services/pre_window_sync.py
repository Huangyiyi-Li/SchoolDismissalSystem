from __future__ import annotations

import datetime

from .schedule_display import is_usable_range, iter_schedule_rules_with_type


def get_next_pre_window_sync_time(schedules, now=None, lead_minutes=2):
    now = now or datetime.datetime.now()
    candidates = []

    for day_offset in range(8):
        target_date = (now + datetime.timedelta(days=day_offset)).date()
        target_weekday = target_date.weekday() + 1

        for _, rule in iter_schedule_rules_with_type(schedules):
            if rule.get("weekday") != target_weekday:
                continue
            for time_range in rule.get("timeRanges") or []:
                if not is_usable_range(time_range):
                    continue
                start_time = time_range.get("startTime")
                if not start_time:
                    continue
                try:
                    start_clock = datetime.datetime.strptime(start_time, "%H:%M").time()
                except ValueError:
                    continue
                trigger_time = datetime.datetime.combine(target_date, start_clock)
                trigger_time -= datetime.timedelta(minutes=lead_minutes)
                if trigger_time > now:
                    candidates.append(trigger_time)

    return min(candidates) if candidates else None
