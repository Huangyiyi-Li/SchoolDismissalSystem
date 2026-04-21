import datetime
import unittest

from src.services.dismissal_window import (
    format_window_label,
    get_active_window_signature,
    is_now_within_window,
)


class DismissalWindowTests(unittest.TestCase):
    def test_dynamic_schedule_window_wins_over_static_fallback(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "08:00", "endTime": "08:30"},
                ],
            }
        ]
        now = datetime.datetime(2026, 4, 21, 8, 15)

        signature = get_active_window_signature(
            schedules,
            "16:30",
            "18:30",
            now=now,
        )

        self.assertEqual(signature, "dynamic:2:08:00-08:30")
        self.assertTrue(
            is_now_within_window(
                schedules,
                "16:30",
                "18:30",
                now=now,
            )
        )

    def test_format_window_label_lists_today_ranges(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "08:00", "endTime": "08:30"},
                    {"startTime": "12:00", "endTime": "12:30"},
                ],
            },
            {
                "weekday": 3,
                "timeRanges": [
                    {"startTime": "15:00", "endTime": "15:30"},
                ],
            },
        ]
        now = datetime.datetime(2026, 4, 21, 16, 45)

        label = format_window_label(
            schedules,
            "16:30",
            "18:30",
            now=now,
        )

        self.assertEqual(label, "今日: 08:00-08:30, 12:00-12:30")

    def test_static_window_still_works_without_schedule(self):
        now = datetime.datetime(2026, 4, 21, 17, 15)

        signature = get_active_window_signature(
            [],
            "16:30",
            "18:30",
            now=now,
        )

        self.assertEqual(signature, "static:16:30-18:30")
        self.assertTrue(
            is_now_within_window(
                [],
                "16:30",
                "18:30",
                now=now,
            )
        )
        self.assertEqual(
            format_window_label(
                [],
                "16:30",
                "18:30",
                now=now,
            ),
            "默认: 16:30 - 18:30",
        )


if __name__ == "__main__":
    unittest.main()
