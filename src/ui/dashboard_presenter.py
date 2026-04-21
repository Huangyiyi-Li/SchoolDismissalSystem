from __future__ import annotations

from dataclasses import dataclass

from src.services.system_status import AlertLevel, DashboardSnapshot


@dataclass(frozen=True)
class DashboardViewModel:
    banner_text: str
    should_pulse: bool
    online_devices_text: str
    window_label: str
    overall_level: AlertLevel


class DashboardPresenter:
    def build(self, snapshot: DashboardSnapshot, online_devices: int, window_label: str) -> DashboardViewModel:
        level_prefix = {
            AlertLevel.OK: "[正常]",
            AlertLevel.WARNING: "[注意]",
            AlertLevel.CRITICAL: "[告警]",
        }.get(snapshot.overall_level, "[状态]")

        banner_text = f"{level_prefix} {snapshot.primary_alert.summary}"
        online_devices_text = f"在线设备: {max(0, int(online_devices))} 台"

        return DashboardViewModel(
            banner_text=banner_text,
            should_pulse=snapshot.should_pulse,
            online_devices_text=online_devices_text,
            window_label=window_label,
            overall_level=snapshot.overall_level,
        )

