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

    def test_format_window_label_shows_unavailable_when_schedule_exists_but_none_today(self):
        schedules = [
            {
                "weekday": 3,
                "timeRanges": [
                    {"startTime": "15:00", "endTime": "15:30"},
                ],
            }
        ]
        now = datetime.datetime(2026, 4, 21, 16, 45)

        label = format_window_label(
            schedules,
            "16:30",
            "18:30",
            now=now,
        )

        self.assertEqual(label, "今日: 无可用时段")

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

    def test_dynamic_schedule_today_outside_ranges_returns_none(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "08:00", "endTime": "08:30"},
                    {"startTime": "12:00", "endTime": "12:30"},
                ],
            }
        ]
        now = datetime.datetime(2026, 4, 21, 9, 0)

        signature = get_active_window_signature(
            schedules,
            "16:30",
            "18:30",
            now=now,
        )

        self.assertIsNone(signature)

    def test_no_schedule_outside_fallback_returns_none(self):
        now = datetime.datetime(2026, 4, 21, 15, 0)

        signature = get_active_window_signature(
            [],
            "16:30",
            "18:30",
            now=now,
        )

        self.assertIsNone(signature)
        self.assertFalse(
            is_now_within_window(
                [],
                "16:30",
                "18:30",
                now=now,
            )
        )

    def test_static_cross_midnight_window_is_supported(self):
        inside_late = datetime.datetime(2026, 4, 21, 23, 30)
        inside_early = datetime.datetime(2026, 4, 22, 0, 30)
        outside = datetime.datetime(2026, 4, 22, 2, 0)

        self.assertEqual(
            get_active_window_signature([], "23:00", "01:00", now=inside_late),
            "static:23:00-01:00",
        )
        self.assertEqual(
            get_active_window_signature([], "23:00", "01:00", now=inside_early),
            "static:23:00-01:00",
        )
        self.assertIsNone(
            get_active_window_signature([], "23:00", "01:00", now=outside),
        )

    def test_dynamic_cross_midnight_window_is_supported(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "23:00", "endTime": "01:00"},
                ],
            }
        ]
        inside_late = datetime.datetime(2026, 4, 21, 23, 30)
        inside_spillover = datetime.datetime(2026, 4, 22, 0, 30)
        outside = datetime.datetime(2026, 4, 22, 2, 0)

        self.assertEqual(
            get_active_window_signature(schedules, "16:30", "18:30", now=inside_late),
            "dynamic:2:23:00-01:00",
        )
        self.assertEqual(
            get_active_window_signature(schedules, "16:30", "18:30", now=inside_spillover),
            "dynamic:2:23:00-01:00",
        )
        self.assertIsNone(
            get_active_window_signature(schedules, "16:30", "18:30", now=outside),
        )

    def test_equal_start_end_window_matches_boundary_only(self):
        boundary = datetime.datetime(2026, 4, 21, 16, 30)
        outside = datetime.datetime(2026, 4, 21, 16, 31)

        self.assertEqual(
            get_active_window_signature([], "16:30", "16:30", now=boundary),
            "static:16:30-16:30",
        )
        self.assertIsNone(
            get_active_window_signature([], "16:30", "16:30", now=outside),
        )

    def test_invalid_schedule_times_are_skipped_safely(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "bad", "endTime": "08:30"},
                    {"startTime": "08:00", "endTime": "08:30"},
                ],
            }
        ]
        now = datetime.datetime(2026, 4, 21, 8, 15)

        self.assertEqual(
            get_active_window_signature(schedules, "16:30", "18:30", now=now),
            "dynamic:2:08:00-08:30",
        )
        self.assertEqual(
            format_window_label(schedules, "16:30", "18:30", now=now),
            "今日: 08:00-08:30",
        )

    def test_invalid_schedule_times_fail_safe_when_no_valid_ranges(self):
        schedules = [
            {
                "weekday": 2,
                "timeRanges": [
                    {"startTime": "xx:yy", "endTime": "08:30"},
                ],
            }
        ]
        now = datetime.datetime(2026, 4, 21, 8, 15)

        self.assertIsNone(
            get_active_window_signature(schedules, "16:30", "18:30", now=now),
        )
        self.assertFalse(
            is_now_within_window(schedules, "16:30", "18:30", now=now),
        )
        self.assertEqual(
            format_window_label(schedules, "16:30", "18:30", now=now),
            "今日: 无可用时段",
        )

    def test_invalid_fallback_times_are_unavailable(self):
        now = datetime.datetime(2026, 4, 21, 17, 15)

        self.assertIsNone(
            get_active_window_signature([], "bad", "18:30", now=now),
        )
        self.assertIsNone(
            get_active_window_signature([], "16:30", "24:99", now=now),
        )
        self.assertFalse(
            is_now_within_window([], "bad", "18:30", now=now),
        )


if __name__ == "__main__":
    unittest.main()
