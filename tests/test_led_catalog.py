import os
import sqlite3
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
            clubs = db.get_led_classes("40125", class_type=2)
            self.assertEqual([item["class_id"] for item in clubs], ["201"])
            self.assertEqual(clubs[0]["class_name"], "足球社团")
            self.assertEqual(len(db.get_all_mappings()), 4)

    def test_status_keys_allow_same_id_for_administrative_and_club_classes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(os.path.join(tmpdir, "school.db"))
            db.save_led_class_status(
                "40125", "101", "2026-08-04", "已放学", class_type=1
            )
            db.save_led_class_status(
                "40125", "101", "2026-08-04", "放学中", class_type=2
            )

            rows = db.get_led_class_statuses("40125", "2026-08-04")

            self.assertEqual(
                [(row["class_type"], row["status"]) for row in rows],
                [(1, "已放学"), (2, "放学中")],
            )

    def test_legacy_status_table_is_migrated_as_administrative_class_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "school.db")
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE led_class_statuses (
                    school_id TEXT NOT NULL,
                    class_id TEXT NOT NULL,
                    status_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dismiss_due_at TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (school_id, class_id, status_date)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO led_class_statuses
                    (school_id, class_id, status_date, status)
                VALUES ('40125', '101', '2026-08-04', '已放学')
                """
            )
            connection.commit()
            connection.close()

            db = DatabaseManager(db_path)

            rows = db.get_led_class_statuses("40125", "2026-08-04")
            self.assertEqual(rows[0]["class_type"], 1)
            self.assertEqual(rows[0]["status"], "已放学")

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
