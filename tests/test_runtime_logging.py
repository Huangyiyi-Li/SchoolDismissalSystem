import os
import tempfile
import unittest

from src.utils.runtime_logging import (
    configure_runtime_logging,
    get_runtime_log_paths,
    shutdown_runtime_logging,
)


class RuntimeLoggingTests(unittest.TestCase):
    def test_runtime_log_paths_use_requested_directory(self):
        paths = get_runtime_log_paths("/tmp/school-dismissal-logs")

        self.assertEqual(paths.runtime_log_path, "/tmp/school-dismissal-logs/runtime.log")
        self.assertEqual(paths.crash_log_path, "/tmp/school-dismissal-logs/crash.log")

    def test_configure_runtime_logging_creates_log_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, "logs")

            try:
                paths = configure_runtime_logging(log_dir)

                self.assertTrue(os.path.isdir(log_dir))
                self.assertTrue(paths.runtime_log_path.endswith("runtime.log"))
                self.assertTrue(paths.crash_log_path.endswith("crash.log"))
            finally:
                shutdown_runtime_logging()


if __name__ == "__main__":
    unittest.main()
