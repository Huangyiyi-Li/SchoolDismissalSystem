from __future__ import annotations

import dataclasses
import datetime as dt
import enum


class AlertLevel(enum.IntEnum):
    OK = 0
    WARNING = 1
    CRITICAL = 2


@dataclasses.dataclass(frozen=True)
class ServiceState:
    name: str
    level: AlertLevel
    message: str = ""
    detail: str = ""
    updated_at: dt.datetime = dataclasses.field(default_factory=dt.datetime.now)

    @classmethod
    def ok(cls, name: str, message: str = "正常", now: dt.datetime | None = None):
        return cls(
            name=name,
            level=AlertLevel.OK,
            message=message,
            detail="",
            updated_at=now or dt.datetime.now(),
        )


@dataclasses.dataclass(frozen=True)
class DashboardSnapshot:
    primary_alert: ServiceState
    should_pulse: bool
    services: dict[str, ServiceState]


class RuntimeStatusStore:
    def __init__(self):
        self._services = {}

    def update(self, key: str, state: ServiceState) -> None:
        self._services[key] = state

    def snapshot(self) -> DashboardSnapshot:
        if not self._services:
            primary = ServiceState(
                name="system",
                level=AlertLevel.WARNING,
                message="等待服务初始化",
            )
        else:
            primary = max(self._services.values(), key=lambda item: item.level)
            if primary.level == AlertLevel.WARNING and primary.name == "udp":
                primary = dataclasses.replace(primary, level=AlertLevel.CRITICAL)

        return DashboardSnapshot(
            primary_alert=primary,
            should_pulse=primary.level == AlertLevel.CRITICAL,
            services=dict(self._services),
        )
