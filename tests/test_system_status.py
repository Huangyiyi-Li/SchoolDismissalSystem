import datetime
import unittest
from dataclasses import fields

from src.services.system_status import (
    AlertLevel,
    DashboardSnapshot,
    RuntimeStatusStore,
    ServiceState,
)


class SystemStatusTests(unittest.TestCase):
    def test_update_rejects_mismatched_service_name(self):
        now = datetime.datetime(2026, 4, 21, 8, 14)
        store = RuntimeStatusStore()
        with self.assertRaises(ValueError):
            store.update(
                "udp",
                ServiceState(
                    name="broadcast",
                    level=AlertLevel.WARNING,
                    summary="bad mapping",
                    detail="wrong key",
                    updated_at=now,
                ),
            )

    def test_warning_is_primary_without_auto_escalation(self):
        now = datetime.datetime(2026, 4, 21, 8, 15)
        store = RuntimeStatusStore()
        store.update(
            "udp",
            ServiceState(
                name="udp",
                level=AlertLevel.WARNING,
                summary="UDP offline",
                detail="socket bind lost",
                updated_at=now,
            ),
        )
        store.update("broadcast", ServiceState.ok("broadcast", "broadcast idle", now))

        snapshot = store.snapshot()

        self.assertIsInstance(snapshot, DashboardSnapshot)
        self.assertEqual(snapshot.overall_level, AlertLevel.WARNING)
        self.assertEqual(snapshot.primary_alert.level, AlertLevel.WARNING)
        self.assertEqual(snapshot.primary_alert.summary, "UDP offline")
        self.assertEqual(snapshot.primary_alert.detail, "socket bind lost")
        self.assertEqual(snapshot.primary_alert.updated_at, now)
        self.assertFalse(snapshot.should_pulse)
        self.assertEqual(snapshot.services["udp"].level, AlertLevel.WARNING)
        self.assertEqual(snapshot.services["udp"].summary, "UDP offline")
        self.assertEqual(snapshot.services["udp"].detail, "socket bind lost")
        self.assertEqual(snapshot.services["udp"].updated_at, now)
        self.assertEqual(
            [field.name for field in fields(DashboardSnapshot)],
            ["overall_level", "primary_alert", "should_pulse", "services"],
        )

    def test_ok_services_produce_quiet_snapshot(self):
        now = datetime.datetime(2026, 4, 21, 8, 16)
        store = RuntimeStatusStore()
        store.update("udp", ServiceState.ok("udp", "udp ok", now))
        store.update("broadcast", ServiceState.ok("broadcast", "broadcast ok", now))

        snapshot = store.snapshot()

        self.assertEqual(snapshot.overall_level, AlertLevel.OK)
        self.assertEqual(snapshot.primary_alert.level, AlertLevel.OK)
        self.assertEqual(snapshot.primary_alert.summary, "udp ok")
        self.assertFalse(snapshot.should_pulse)
        self.assertTrue(all(state.level == AlertLevel.OK for state in snapshot.services.values()))
        self.assertEqual(
            [field.name for field in fields(ServiceState)],
            ["name", "level", "summary", "detail", "updated_at"],
        )
        self.assertEqual(
            [field.name for field in fields(DashboardSnapshot)],
            ["overall_level", "primary_alert", "should_pulse", "services"],
        )

    def test_critical_service_pulses(self):
        now = datetime.datetime(2026, 4, 21, 8, 17)
        store = RuntimeStatusStore()
        store.update("udp", ServiceState.ok("udp", "udp ok", now))
        store.update(
            "broadcast",
            ServiceState(
                name="broadcast",
                level=AlertLevel.CRITICAL,
                summary="tts unavailable",
                detail="driver init failed",
                updated_at=now,
            ),
        )

        snapshot = store.snapshot()

        self.assertEqual(snapshot.overall_level, AlertLevel.CRITICAL)
        self.assertEqual(snapshot.primary_alert.name, "broadcast")
        self.assertEqual(snapshot.primary_alert.level, AlertLevel.CRITICAL)
        self.assertTrue(snapshot.should_pulse)


if __name__ == "__main__":
    unittest.main()
