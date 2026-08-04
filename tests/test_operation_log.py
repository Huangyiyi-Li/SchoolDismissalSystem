import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.services.operation_log import OperationLogManager


class OperationLogTests(unittest.TestCase):
    def test_records_and_reads_a_local_operation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = OperationLogManager(
                log_dir=tmpdir,
                clock=lambda: "2026-08-04 09:10:11",
            )

            entry = logger.record(
                category="LED 屏",
                action="刷新放学节目",
                target="192.168.100.1:5005",
                result="success",
                detail="已启动 3 个 LED 页面轮播",
                source="本机",
            )

            self.assertEqual(logger.get_recent_entries(limit=1), [entry])
            log_path = os.path.join(tmpdir, "operation-2026-08-04-01.jsonl")
            with open(log_path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.loads(handle.readline()), entry)

    def test_suppresses_identical_high_frequency_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = OperationLogManager(
                log_dir=tmpdir,
                clock=lambda: "2026-08-04 09:10:11",
                dedup_interval_seconds=10,
            )

            with patch("src.services.operation_log.time.monotonic", side_effect=[1.0, 2.0]):
                logger.record("LED 屏", "刷新放学节目", result="fail", detail="offline")
                logger.record("LED 屏", "刷新放学节目", result="fail", detail="offline")

            self.assertEqual(len(logger.get_recent_entries()), 1)

    def test_rotates_small_files_and_keeps_a_bounded_file_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dates = iter(
                [
                    "2026-08-01 09:00:00",
                    "2026-08-02 09:00:00",
                    "2026-08-03 09:00:00",
                ]
            )
            logger = OperationLogManager(
                log_dir=tmpdir,
                clock=lambda: next(dates),
                max_file_bytes=1,
                max_files=2,
                dedup_interval_seconds=0,
            )

            logger.record("系统", "启动", detail="first")
            logger.record("系统", "启动", detail="second")
            logger.record("系统", "启动", detail="third")

            files = sorted(os.path.basename(path) for path in os.scandir(tmpdir))
            self.assertEqual(
                files,
                ["operation-2026-08-02-01.jsonl", "operation-2026-08-03-01.jsonl"],
            )


if __name__ == "__main__":
    unittest.main()
