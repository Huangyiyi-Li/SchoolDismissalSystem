import json
import os
import tempfile
import unittest

from src.services.network_log import NetworkLogManager


class NetworkLogTests(unittest.TestCase):
    def test_record_writes_jsonl_and_reads_recent_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = NetworkLogManager(
                log_dir=tmpdir,
                clock=lambda: "2026-05-28 09:10:11",
            )

            logger.record(
                protocol="HTTP",
                direction="OUT",
                target="/kq-http/school-dismissal-system/get-classes-v2",
                request={"schoolId": "40125"},
                response={"code": 200},
                elapsed_ms=12,
                result="success",
            )

            log_path = os.path.join(tmpdir, "network-2026-05-28.jsonl")
            with open(log_path, "r", encoding="utf-8") as f:
                line = f.readline()
            entry = json.loads(line)

            self.assertEqual(entry["timestamp"], "2026-05-28 09:10:11")
            self.assertEqual(entry["protocol"], "HTTP")
            self.assertEqual(entry["direction"], "OUT")
            self.assertEqual(entry["target"], "/kq-http/school-dismissal-system/get-classes-v2")
            self.assertEqual(entry["request"], {"schoolId": "40125"})
            self.assertEqual(entry["response"], {"code": 200})

            self.assertEqual(logger.get_recent_entries(limit=1), [entry])


if __name__ == "__main__":
    unittest.main()
