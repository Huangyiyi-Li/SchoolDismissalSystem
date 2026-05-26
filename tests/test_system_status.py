import unittest

from src.services.system_status import (
    AlertLevel,
    RuntimeStatusStore,
    ServiceState,
)


class SystemStatusTests(unittest.TestCase):
    def test_warning_becomes_critical_when_udp_is_down(self):
        store = RuntimeStatusStore()
        store.update("udp", ServiceState(name="udp", level=AlertLevel.WARNING, message="offline"))
        store.update("broadcast", ServiceState.ok("broadcast"))

        snapshot = store.snapshot()

        self.assertEqual(snapshot.primary_alert.level, AlertLevel.CRITICAL)
        self.assertTrue(snapshot.should_pulse)
        self.assertEqual(snapshot.services["udp"].level, AlertLevel.WARNING)

    def test_ok_services_produce_quiet_snapshot(self):
        store = RuntimeStatusStore()
        store.update("udp", ServiceState.ok("udp"))
        store.update("broadcast", ServiceState.ok("broadcast"))

        snapshot = store.snapshot()

        self.assertEqual(snapshot.primary_alert.level, AlertLevel.OK)
        self.assertFalse(snapshot.should_pulse)
        self.assertTrue(all(state.level == AlertLevel.OK for state in snapshot.services.values()))


if __name__ == "__main__":
    unittest.main()
