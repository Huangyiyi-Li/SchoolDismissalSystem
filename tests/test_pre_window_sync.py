import datetime
import unittest

from src.services.pre_window_sync import get_next_pre_window_sync_time


class PreWindowSyncTests(unittest.TestCase):
    def test_returns_two_minutes_before_nearest_schedule_start(self):
        schedules = [
            {
                "classType": 1,
                "schedules": [
                    {
                        "weekday": 1,
                        "timeRanges": [
                            {"startTime": "15:30", "endTime": "16:00"},
                            {"startTime": "17:00", "endTime": "17:30"},
                        ],
                    }
                ],
            }
        ]
        now = datetime.datetime(2026, 6, 15, 14, 0)

        self.assertEqual(
            get_next_pre_window_sync_time(schedules, now),
            datetime.datetime(2026, 6, 15, 15, 28),
        )

    def test_uses_next_week_when_todays_trigger_has_passed(self):
        schedules = [
            {
                "classType": 2,
                "schedules": [
                    {
                        "weekday": 1,
                        "timeRanges": [
                            {"startTime": "15:30", "endTime": "16:00"},
                        ],
                    }
                ],
            }
        ]
        now = datetime.datetime(2026, 6, 15, 15, 29)

        self.assertEqual(
            get_next_pre_window_sync_time(schedules, now),
            datetime.datetime(2026, 6, 22, 15, 28),
        )

    def test_ignores_disabled_midnight_range(self):
        schedules = [
            {
                "classType": 1,
                "schedules": [
                    {
                        "weekday": 1,
                        "timeRanges": [
                            {"startTime": "00:00", "endTime": "00:00"},
                        ],
                    }
                ],
            }
        ]

        self.assertIsNone(
            get_next_pre_window_sync_time(
                schedules,
                datetime.datetime(2026, 6, 15, 14, 0),
            )
        )


if __name__ == "__main__":
    unittest.main()
