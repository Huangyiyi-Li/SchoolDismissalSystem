import os
import tempfile
import unittest

from src.database import DatabaseManager
from src.services.data_sync_service import DataSyncWorker


class FakeConfig:
    def get(self, key, default=None):
        return default


class CatalogApi:
    school_id = "40125"

    def get_classes(self):
        return [
            {
                "classType": 1,
                "classId": "101",
                "gradeName": "一年级",
                "className": "一年级一班",
                "classShowName": "一(1)班",
                "classVoiceName": "一年级一班",
                "cardId": "A1,B2",
            },
            {
                "classType": 1,
                "classId": "102",
                "gradeName": "一年级",
                "className": "一年级二班",
                "classShowName": "一(2)班",
                "classVoiceName": "一年级二班",
                "cardId": "C3",
            },
            {
                "classType": 2,
                "classId": "201",
                "gradeName": "",
                "className": "足球社团",
                "cardId": "D4",
            },
        ]


class EmptyCatalogApi(CatalogApi):
    def get_classes(self):
        return []


class LedCatalogTests(unittest.TestCase):
    def test_sync_deduplicates_classes_independently_from_card_mappings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(os.path.join(tmpdir, "school.db"))

            DataSyncWorker(CatalogApi(), db, FakeConfig()).sync_classes(clear_existing=True)

            classes = db.get_led_classes("40125")
            self.assertEqual([item["class_id"] for item in classes], ["101", "102"])
            self.assertEqual(classes[0]["grade_name"], "一年级")
            self.assertEqual(len(db.get_all_mappings()), 4)

    def test_clear_mappings_also_clears_led_class_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(os.path.join(tmpdir, "school.db"))
            DataSyncWorker(CatalogApi(), db, FakeConfig()).sync_classes()

            db.clear_mappings()

            self.assertEqual(db.get_led_classes("40125"), [])

    def test_successful_empty_server_list_clears_stale_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(os.path.join(tmpdir, "school.db"))
            DataSyncWorker(CatalogApi(), db, FakeConfig()).sync_classes()

            DataSyncWorker(EmptyCatalogApi(), db, FakeConfig()).sync_classes(clear_existing=True)

            self.assertEqual(db.get_led_classes("40125"), [])


if __name__ == "__main__":
    unittest.main()
