import os
import tempfile
import unittest

from src.database import DatabaseManager
from src.services.log_records import format_log_timestamp


class LogRecordTests(unittest.TestCase):
    def test_log_timestamp_preserves_full_date_and_time(self):
        self.assertEqual(
            format_log_timestamp("2026-05-21 17:10:30"),
            "2026-05-21 17:10:30",
        )

    def test_log_timestamp_keeps_legacy_values_if_parse_fails(self):
        self.assertEqual(format_log_timestamp("17:10:30"), "17:10:30")

    def test_swipe_logs_survive_new_database_manager_instance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "school.db")
            first_db = DatabaseManager(db_path=db_path)
            first_db.log_swipe("1001", "四年级七班", "语音播报 (正常)")

            second_db = DatabaseManager(db_path=db_path)
            logs = second_db.get_recent_logs()

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0][1], "1001")
            self.assertEqual(logs[0][2], "四年级七班")
            self.assertEqual(logs[0][3], "语音播报 (正常)")

    def test_structured_logs_describe_swipe_and_server_command_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=os.path.join(tmpdir, "school.db"))
            db.log_swipe(
                "1001",
                "一年级一班",
                "语音播报 (正常)",
                source="刷卡",
                source_detail="1001",
                class_type=1,
            )
            db.log_swipe(
                "",
                "足球社团",
                "语音播报 (服务端指令)",
                source="服务端指令",
                class_type=2,
            )

            logs = db.get_recent_log_records(limit=2)

            self.assertEqual(logs[0]["source"], "服务端指令")
            self.assertEqual(logs[0]["source_detail"], "")
            self.assertEqual(logs[0]["class_type"], 2)
            self.assertEqual(logs[0]["class_name"], "足球社团")
            self.assertEqual(logs[1]["source"], "刷卡")
            self.assertEqual(logs[1]["source_detail"], "1001")
            self.assertEqual(logs[1]["class_type"], 1)


if __name__ == "__main__":
    unittest.main()
