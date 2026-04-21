import datetime
import unittest

from src.services.system_status import AlertLevel, DashboardSnapshot, ServiceState
from src.ui.dashboard_presenter import DashboardPresenter


class DashboardPresenterTests(unittest.TestCase):
    def test_critical_snapshot_builds_pulsing_banner(self):
        now = datetime.datetime(2026, 4, 21, 10, 5, 0)
        snapshot = DashboardSnapshot(
            overall_level=AlertLevel.CRITICAL,
            primary_alert=ServiceState(
                name="udp",
                level=AlertLevel.CRITICAL,
                summary="udp down",
                detail="bind failed",
                updated_at=now,
            ),
            should_pulse=True,
            services={},
        )
        presenter = DashboardPresenter()

        vm = presenter.build(snapshot=snapshot, online_devices=2, window_label="今日: 16:30-18:30")

        self.assertEqual(vm.overall_level, AlertLevel.CRITICAL)
        self.assertTrue(vm.should_pulse)
        self.assertIn("udp down", vm.banner_text)

    def test_online_devices_text_formatting(self):
        now = datetime.datetime(2026, 4, 21, 10, 6, 0)
        snapshot = DashboardSnapshot(
            overall_level=AlertLevel.OK,
            primary_alert=ServiceState.ok("system", "system nominal", now),
            should_pulse=False,
            services={},
        )
        presenter = DashboardPresenter()

        vm = presenter.build(snapshot=snapshot, online_devices=3, window_label="默认: 16:30 - 18:30")

        self.assertEqual(vm.online_devices_text, "在线设备: 3 台")


if __name__ == "__main__":
    unittest.main()

