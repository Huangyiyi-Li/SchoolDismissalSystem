import os
import tempfile
import unittest

from src.database import DatabaseManager
from src.services.data_sync_service import DataSyncWorker


class FakeApi:
    school_id = "40125"

    def get_classes(self):
        return [
            {
                "classType": 1,
                "classId": "101",
                "className": "一年级一班",
                "classShowName": "一(1)班",
                "classVoiceName": "一年级一班",
                "cardId": "A1,B2",
            },
            {
                "classType": 2,
                "classId": "201",
                "className": "足球社团",
                "classShowName": "足球社团",
                "classVoiceName": "足球社团",
                "cardId": ["C3"],
            },
        ]

    def get_school_dismissal_schedule(self):
        return [
            {
                "schoolId": "40125",
                "classType": 1,
                "schedules": [
                    {
                        "weekday": 1,
                        "timeRanges": [{"startTime": "15:30", "endTime": "16:00"}],
                    }
                ],
            }
        ]


class FakeConfig:
    def __init__(self):
        self.values = {}
        self.saved = False

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.saved = True


class DataSyncV2Tests(unittest.TestCase):
    def test_sync_all_replaces_existing_mappings_with_server_class_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=os.path.join(tmpdir, "school.db"))
            db.add_mapping("A1", "旧名称", class_id="old-1", school_id="40125")
            worker = DataSyncWorker(FakeApi(), db, FakeConfig())

            worker.sync_all()

            self.assertEqual(
                db.get_class_info_by_card("A1"),
                ("一年级一班", "101", "40125", 1, "一(1)班", "一年级一班"),
            )

    def test_sync_classes_persists_class_type_and_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=os.path.join(tmpdir, "school.db"))
            worker = DataSyncWorker(FakeApi(), db, FakeConfig())

            worker.sync_classes()

            self.assertEqual(
                db.get_class_info_by_card("A1"),
                ("一年级一班", "101", "40125", 1, "一(1)班", "一年级一班"),
            )
            self.assertEqual(
                db.get_class_info_by_card("C3"),
                ("足球社团", "201", "40125", 2, "足球社团", "足球社团"),
            )

    def test_sync_classes_clears_mappings_for_previous_school(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=os.path.join(tmpdir, "school.db"))
            db.add_mapping(
                "OLD",
                "旧学校班级",
                class_id="old-1",
                school_id="old-school",
                class_type=1,
            )
            worker = DataSyncWorker(FakeApi(), db, FakeConfig())

            worker.sync_classes(clear_existing=True)

            self.assertEqual(db.get_class_info_by_card("OLD")[0], None)
            self.assertEqual(db.get_class_info_by_card("A1")[2], "40125")

    def test_sync_schedule_saves_v2_grouped_schedule(self):
        config = FakeConfig()
        worker = DataSyncWorker(FakeApi(), object(), config)

        worker.sync_schedule()

        self.assertEqual(config.values["schedules"][0]["classType"], 1)
        self.assertTrue(config.saved)


if __name__ == "__main__":
    unittest.main()
