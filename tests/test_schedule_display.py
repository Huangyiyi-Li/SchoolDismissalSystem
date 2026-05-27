import unittest

from src.services.schedule_display import group_schedules_by_weekday_and_type


class ScheduleDisplayTests(unittest.TestCase):
    def test_group_schedules_by_weekday_then_class_type(self):
        schedules = [
            {
                "classType": 2,
                "schedules": [
                    {
                        "weekday": 3,
                        "timeRanges": [{"startTime": "17:30", "endTime": "18:00"}],
                    }
                ],
            },
            {
                "classType": 1,
                "schedules": [
                    {
                        "weekday": 3,
                        "timeRanges": [{"startTime": "16:30", "endTime": "17:00"}],
                    }
                ],
            },
        ]

        grouped = group_schedules_by_weekday_and_type(schedules)

        self.assertEqual(
            grouped[3][1],
            [{"startTime": "16:30", "endTime": "17:00"}],
        )
        self.assertEqual(
            grouped[3][2],
            [{"startTime": "17:30", "endTime": "18:00"}],
        )


if __name__ == "__main__":
    unittest.main()
