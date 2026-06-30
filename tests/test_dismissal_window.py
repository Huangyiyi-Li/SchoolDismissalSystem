import datetime
import unittest

from src.services.dismissal_window import (
    format_grouped_window_label,
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

        self.assertEqual(label, "2026 年 4 月 21 日 星期二\n08:00-08:30\n12:00-12:30")

    def test_static_window_still_works_without_schedule(self):
        now = datetime.datetime(2026, 4, 21, 17, 15)

        signature = get_active_window_signature(
            None,
            "16:30",
            "18:30",
            now=now,
        )

        self.assertEqual(signature, "static:16:30-18:30")
        self.assertTrue(
            is_now_within_window(
                None,
                "16:30",
                "18:30",
                now=now,
            )
        )
        self.assertEqual(
            format_window_label(
                None,
                "16:30",
                "18:30",
                now=now,
            ),
            "默认: 16:30 - 18:30",
        )

    def test_empty_server_schedule_does_not_use_static_fallback(self):
        now = datetime.datetime(2026, 4, 21, 17, 15)

        self.assertIsNone(
            get_active_window_signature(
                [],
                "16:30",
                "18:30",
                now=now,
            )
        )
        self.assertEqual(
            format_window_label([], "16:30", "18:30", now=now),
            "未配置",
        )
        grouped = format_grouped_window_label([], "16:30", "18:30", now=now)
        self.assertNotIn("默认:", grouped)
        self.assertEqual(grouped.count("未配置"), 2)

    def test_format_grouped_window_label_splits_class_types(self):
        schedules = [
            {
                "classType": 1,
                "schedules": [
                    {
                        "weekday": 3,
                        "timeRanges": [
                            {"startTime": "06:30", "endTime": "08:30"},
                            {"startTime": "16:30", "endTime": "17:00"},
                        ],
                    }
                ],
            },
            {
                "classType": 2,
                "schedules": [
                    {
                        "weekday": 3,
                        "timeRanges": [
                            {"startTime": "17:30", "endTime": "18:00"},
                        ],
                    }
                ],
            },
        ]
        now = datetime.datetime(2026, 5, 27, 12, 0)

        self.assertEqual(
            format_grouped_window_label(
                schedules,
                "16:30",
                "18:30",
                now=now,
            ),
            (
                "2026 年 5 月 27 日 星期三\n\n"
                "行政班放学时段\n"
                "06:30-08:30\n"
                "16:30-17:00\n\n"
                "社团班放学时段\n"
                "17:30-18:00"
            ),
        )

    def test_grouped_window_label_accepts_string_class_type(self):
        schedules = [
            {
                "classType": "1",
                "schedules": [
                    {
                        "weekday": 3,
                        "timeRanges": [{"startTime": "16:30", "endTime": "17:00"}],
                    }
                ],
            }
        ]
        now = datetime.datetime(2026, 5, 27, 12, 0)

        self.assertIn(
            "行政班放学时段\n16:30-17:00",
            format_grouped_window_label(
                schedules,
                "16:30",
                "18:30",
                now=now,
            ),
        )


if __name__ == "__main__":
    unittest.main()
