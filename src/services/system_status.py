from __future__ import annotations

import datetime as _dt
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
    summary: str
    detail: str = ""
    updated_at: _dt.datetime = field(default_factory=_dt.datetime.now)

    @classmethod
    def ok(cls, name: str, summary: str, now: _dt.datetime | None = None) -> "ServiceState":
        return cls(
            name=name,
            level=AlertLevel.OK,
            summary=summary,
            detail="",
            updated_at=now or _dt.datetime.now(),
        )


@dataclass(frozen=True)
class DashboardSnapshot:
    overall_level: AlertLevel
    primary_alert: ServiceState = field(
        default_factory=lambda: ServiceState.ok("system", "system nominal")
    )
    should_pulse: bool = False
    services: dict[str, ServiceState] = field(default_factory=dict)


class RuntimeStatusStore:
    def __init__(self):
        self._services: dict[str, ServiceState] = {}

    def update(self, name: str, state: ServiceState) -> None:
        self._services[name] = state

    def snapshot(self) -> DashboardSnapshot:
        services = dict(self._services)
        if not services:
            primary = ServiceState.ok("system", "system nominal")
            return DashboardSnapshot(
                overall_level=AlertLevel.OK,
                primary_alert=primary,
                should_pulse=False,
                services=services,
            )

        severity = {
            AlertLevel.OK: 0,
            AlertLevel.WARNING: 1,
            AlertLevel.CRITICAL: 2,
        }
        _, primary_state = max(
            services.items(),
            key=lambda item: (severity[item[1].level], item[0]),
        )

        overall_level = primary_state.level
        should_pulse = primary_state.level == AlertLevel.CRITICAL
        return DashboardSnapshot(
            overall_level=overall_level,
            primary_alert=primary_state,
            should_pulse=should_pulse,
            services=services,
        )
