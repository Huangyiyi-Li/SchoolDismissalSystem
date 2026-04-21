from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AlertLevel(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2


@dataclass(frozen=True)
class ServiceState:
    name: str
    level: AlertLevel
    message: str = ""

    @classmethod
    def ok(cls, name: str, message: str = "") -> "ServiceState":
        return cls(name=name, level=AlertLevel.OK, message=message)


@dataclass(frozen=True)
class DashboardSnapshot:
    services: dict[str, ServiceState] = field(default_factory=dict)
    primary_alert: ServiceState = field(default_factory=lambda: ServiceState.ok("system"))
    should_pulse: bool = False


class RuntimeStatusStore:
    def __init__(self):
        self._services: dict[str, ServiceState] = {}

    def update(self, name: str, state: ServiceState) -> None:
        self._services[name] = state

    def snapshot(self) -> DashboardSnapshot:
        services = dict(self._services)
        if not services:
            primary = ServiceState.ok("system")
            return DashboardSnapshot(services=services, primary_alert=primary, should_pulse=False)

        severity = {
            AlertLevel.OK: 0,
            AlertLevel.WARNING: 1,
            AlertLevel.CRITICAL: 2,
        }
        primary_name, primary_state = max(
            services.items(),
            key=lambda item: (severity[item[1].level], item[0]),
        )

        if primary_state.level == AlertLevel.WARNING and primary_name == "udp":
            primary_state = ServiceState(
                name=primary_state.name,
                level=AlertLevel.CRITICAL,
                message=primary_state.message,
            )

        should_pulse = primary_state.level == AlertLevel.CRITICAL
        return DashboardSnapshot(
            services=services,
            primary_alert=primary_state,
            should_pulse=should_pulse,
        )
