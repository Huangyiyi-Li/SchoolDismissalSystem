import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.led_bridge_client import JavaLedBridge, WINDOWS_CREATE_NO_WINDOW


class LedBridgeClientTests(unittest.TestCase):
    def test_ping_uses_configured_ip_and_port(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, "OK connected\n", "")

        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = JavaLedBridge(Path(tmpdir), java_command="java", runner=runner)
            result = bridge.ping("192.168.100.1", 5005)

        self.assertTrue(result.ok)
        self.assertIn("192.168.100.1", calls[0][0])
        self.assertIn("5005", calls[0][0])
        self.assertIn("ping", calls[0][0])

    def test_display_passes_all_generated_pages_and_stay_time(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "OK displayed\n", "")

        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = JavaLedBridge(Path(tmpdir), runner=runner)
            pages = [Path(tmpdir) / "page-1.bmp", Path(tmpdir) / "page-2.bmp"]

            result = bridge.display(
                "10.0.0.8",
                5005,
                pages,
                stay_seconds=7,
                width=640,
                height=80,
            )

        self.assertTrue(result.ok)
        self.assertIn("700", calls[0])
        self.assertIn("640", calls[0])
        self.assertIn("80", calls[0])
        self.assertLess(calls[0].index("--width"), calls[0].index("--images"))
        self.assertEqual(calls[0][-2:], [str(page.resolve()) for page in pages])

    def test_nonzero_bridge_exit_is_returned_as_failure(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, "", "ERR timeout")

        bridge = JavaLedBridge(Path("/missing"), runner=runner)

        result = bridge.clear("192.168.100.1", 5005)

        self.assertFalse(result.ok)
        self.assertIn("timeout", result.message)

    def test_display_has_longer_timeout_than_ping(self):
        timeouts = []

        def runner(command, **kwargs):
            timeouts.append(kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0, "OK\n", "")

        bridge = JavaLedBridge(Path("/bridge"), runner=runner)

        bridge.ping("192.168.100.1", 5005)
        bridge.display("192.168.100.1", 5005, [Path("/tmp/page.bmp")])

        self.assertEqual(timeouts, [20, 60])

    def test_windows_java_process_is_started_without_console_window(self):
        class FakeProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return ("OK\n", "")

        bridge = JavaLedBridge(Path("C:/bridge"), java_command="java.exe")
        with patch("src.services.led_bridge_client.os.name", "nt"), patch(
            "src.services.led_bridge_client.subprocess.Popen",
            return_value=FakeProcess(),
        ) as popen:
            bridge._run_default(["java.exe", "-version"], 20)

        self.assertEqual(
            popen.call_args.kwargs["creationflags"],
            WINDOWS_CREATE_NO_WINDOW,
        )


if __name__ == "__main__":
    unittest.main()
