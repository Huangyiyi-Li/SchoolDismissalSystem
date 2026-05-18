# Windows Dashboard Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Windows client into a guarded dashboard with a hidden maintenance mode while tightening long-running runtime stability and preserving low memory usage.

**Architecture:** Keep the app as a single native `PyQt6` process. Extract schedule, alert, UDP parsing, and maintenance-session logic into testable modules, then rebuild the main window around a dashboard view plus a protected maintenance panel backed by explicit runtime status objects.

**Tech Stack:** Python 3, PyQt6, sqlite3, pyttsx3, unittest, PyInstaller

---

### Task 1: Extract and test scheduling + status primitives

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_dismissal_window.py`
- Create: `tests/test_system_status.py`
- Create: `src/services/dismissal_window.py`
- Create: `src/services/system_status.py`

- [ ] **Step 1: Write the failing schedule and status tests**

```python
# tests/test_dismissal_window.py
import datetime
import unittest

from src.services.dismissal_window import (
    format_window_label,
    get_active_window_signature,
    is_now_within_window,
)


class DismissalWindowTests(unittest.TestCase):
    def test_dynamic_schedule_window_wins_over_static_fallback(self):
        now = datetime.datetime(2026, 4, 21, 16, 45)
        schedules = [
            {"weekday": 2, "timeRanges": [{"startTime": "16:30", "endTime": "17:10"}]}
        ]

        signature = get_active_window_signature(
            schedules=schedules,
            fallback_start="15:00",
            fallback_end="18:00",
            now=now,
        )

        self.assertEqual(signature, "WD2_16:30-17:10")

    def test_format_window_label_lists_today_ranges(self):
        now = datetime.datetime(2026, 4, 21, 16, 45)
        schedules = [
            {"weekday": 2, "timeRanges": [{"startTime": "16:30", "endTime": "17:10"}]}
        ]

        self.assertEqual(
            format_window_label(schedules, "16:30", "18:30", now),
            "今日: 16:30-17:10",
        )

    def test_static_window_still_works_without_schedule(self):
        now = datetime.datetime(2026, 4, 21, 17, 5)
        self.assertTrue(is_now_within_window([], "16:30", "18:30", now))


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_system_status.py
import datetime
import unittest

from src.services.system_status import (
    AlertLevel,
    RuntimeStatusStore,
    ServiceState,
)


class RuntimeStatusStoreTests(unittest.TestCase):
    def test_warning_becomes_critical_when_udp_is_down(self):
        store = RuntimeStatusStore()
        now = datetime.datetime(2026, 4, 21, 16, 45)

        store.update(
            "udp",
            ServiceState(
                name="udp",
                level=AlertLevel.CRITICAL,
                summary="UDP监听中断",
                detail="端口 39169 绑定失败",
                updated_at=now,
            ),
        )

        snapshot = store.snapshot(now)

        self.assertEqual(snapshot.overall_level, AlertLevel.CRITICAL)
        self.assertEqual(snapshot.primary_alert, "UDP监听中断")
        self.assertTrue(snapshot.should_pulse)

    def test_ok_services_produce_quiet_snapshot(self):
        store = RuntimeStatusStore()
        now = datetime.datetime(2026, 4, 21, 16, 45)

        store.update("udp", ServiceState.ok("udp", "UDP监听正常", now))
        store.update("tts", ServiceState.ok("tts", "语音播报正常", now))

        snapshot = store.snapshot(now)

        self.assertEqual(snapshot.overall_level, AlertLevel.OK)
        self.assertFalse(snapshot.should_pulse)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_dismissal_window tests.test_system_status -v
```

Expected: `ModuleNotFoundError` for `src.services.dismissal_window` and `src.services.system_status`.

- [ ] **Step 3: Write the minimal scheduling and status modules**

```python
# src/services/dismissal_window.py
from __future__ import annotations

import datetime as dt
from typing import Iterable


def _parse_clock(value: str) -> dt.time:
    return dt.datetime.strptime(value, "%H:%M").time()


def get_active_window_signature(schedules, fallback_start, fallback_end, now=None):
    now = now or dt.datetime.now()
    current_weekday = now.weekday() + 1
    current_time = now.time()

    for rule in schedules or []:
        if rule.get("weekday") != current_weekday:
            continue
        for time_range in rule.get("timeRanges", []):
            start = _parse_clock(time_range["startTime"])
            end = _parse_clock(time_range["endTime"])
            if start <= current_time <= end:
                return f"WD{current_weekday}_{time_range['startTime']}-{time_range['endTime']}"

    if schedules:
        return None

    start = _parse_clock(fallback_start)
    end = _parse_clock(fallback_end)
    if start <= current_time <= end:
        return f"Static_{fallback_start}-{fallback_end}"
    return None


def is_now_within_window(schedules, fallback_start, fallback_end, now=None):
    return get_active_window_signature(schedules, fallback_start, fallback_end, now) is not None


def format_window_label(schedules, fallback_start, fallback_end, now=None):
    now = now or dt.datetime.now()
    current_weekday = now.weekday() + 1
    today_ranges = []
    for rule in schedules or []:
        if rule.get("weekday") != current_weekday:
            continue
        for time_range in rule.get("timeRanges", []):
            today_ranges.append(f"{time_range['startTime']}-{time_range['endTime']}")
    if today_ranges:
        return "今日: " + ", ".join(today_ranges)
    return f"默认: {fallback_start} - {fallback_end}"
```

```python
# src/services/system_status.py
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
    summary: str
    detail: str
    updated_at: dt.datetime

    @classmethod
    def ok(cls, name: str, summary: str, now: dt.datetime) -> "ServiceState":
        return cls(name=name, level=AlertLevel.OK, summary=summary, detail="", updated_at=now)


@dataclasses.dataclass(frozen=True)
class DashboardSnapshot:
    overall_level: AlertLevel
    primary_alert: str
    should_pulse: bool
    services: dict[str, ServiceState]


class RuntimeStatusStore:
    def __init__(self):
        self._services: dict[str, ServiceState] = {}

    def update(self, key: str, state: ServiceState) -> None:
        self._services[key] = state

    def snapshot(self, now: dt.datetime | None = None) -> DashboardSnapshot:
        now = now or dt.datetime.now()
        if not self._services:
            return DashboardSnapshot(AlertLevel.WARNING, "等待服务初始化", False, {})
        top_state = max(self._services.values(), key=lambda item: item.level)
        return DashboardSnapshot(
            overall_level=top_state.level,
            primary_alert=top_state.summary,
            should_pulse=top_state.level == AlertLevel.CRITICAL,
            services=dict(self._services),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_dismissal_window tests.test_system_status -v
```

Expected: all tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/test_dismissal_window.py tests/test_system_status.py src/services/dismissal_window.py src/services/system_status.py
git commit -m "feat: add dashboard scheduling and status primitives"
```

### Task 2: Extract UDP parsing and broadcast decision logic

**Files:**
- Create: `tests/test_udp_parser.py`
- Create: `tests/test_broadcast_policy.py`
- Create: `src/services/udp_parser.py`
- Create: `src/services/broadcast_policy.py`
- Modify: `src/services/config_manager.py`
- Modify: `src/services/udp_server.py`
- Modify: `src/services/broadcast_manager.py`
- Modify: `src/services/data_sync_service.py`

- [ ] **Step 1: Write the failing UDP parser and broadcast policy tests**

```python
# tests/test_udp_parser.py
import unittest

from src.services.udp_parser import parse_udp_packet


class UdpParserTests(unittest.TestCase):
    def test_parses_sequence_and_card_id_from_valid_packet(self):
        packet = bytes.fromhex("C1 01 02 03 04 05 06 09 08 07 78 56 34 12 00 00 00 00 00 00 00 00")

        result = parse_udp_packet(packet)

        self.assertEqual(result.sequence_id, 9)
        self.assertEqual(result.card_id, "305419896")

    def test_rejects_invalid_header(self):
        with self.assertRaises(ValueError):
            parse_udp_packet(bytes.fromhex("B0 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"))


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_broadcast_policy.py
import datetime
import unittest

from src.services.broadcast_policy import evaluate_swipe


class BroadcastPolicyTests(unittest.TestCase):
    def test_broadcast_count_is_applied_to_voice_text(self):
        now = datetime.datetime(2026, 4, 21, 16, 45)

        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="class-1",
            card_id="1001",
            window_signature="WD2_16:30-17:10",
            voice_history={},
            api_push_history={},
            now=now,
            deduplication_interval_seconds=300,
            broadcast_count=2,
            test_mode=False,
            api_available=True,
        )

        self.assertEqual(decision.voice_text, "一年级一班正在放学，一年级一班正在放学")
        self.assertTrue(decision.should_push_api)

    def test_duplicate_window_skips_voice_and_marks_reason(self):
        now = datetime.datetime(2026, 4, 21, 16, 46)

        decision = evaluate_swipe(
            class_name="一年级一班",
            class_id="class-1",
            card_id="1001",
            window_signature="WD2_16:30-17:10",
            voice_history={"一年级一班": "WD2_16:30-17:10"},
            api_push_history={"1001": now},
            now=now,
            deduplication_interval_seconds=300,
            broadcast_count=3,
            test_mode=False,
            api_available=True,
        )

        self.assertFalse(decision.should_voice)
        self.assertIn("重复播报", decision.reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_udp_parser tests.test_broadcast_policy -v
```

Expected: `ModuleNotFoundError` for `src.services.udp_parser` and `src.services.broadcast_policy`.

- [ ] **Step 3: Write the parser and policy modules**

```python
# src/services/udp_parser.py
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ParsedPacket:
    sequence_id: int
    card_id: str


def parse_udp_packet(data: bytes) -> ParsedPacket:
    if len(data) != 22:
        raise ValueError(f"Invalid packet length: {len(data)}")
    if data[0] != 0xC1:
        raise ValueError(f"Invalid packet header: {data[0]:02X}")
    sequence_id = data[7]
    card_id = str(int.from_bytes(data[10:14], byteorder="little"))
    return ParsedPacket(sequence_id=sequence_id, card_id=card_id)
```

```python
# src/services/broadcast_policy.py
from __future__ import annotations

import dataclasses
import datetime as dt


@dataclasses.dataclass(frozen=True)
class SwipeDecision:
    should_voice: bool
    voice_text: str
    should_push_api: bool
    action: str
    reason: str


def evaluate_swipe(
    class_name,
    class_id,
    card_id,
    window_signature,
    voice_history,
    api_push_history,
    now,
    deduplication_interval_seconds,
    broadcast_count,
    test_mode,
    api_available,
):
    should_voice = voice_history.get(class_name) != window_signature
    action = "语音播报" if should_voice else "语音跳过"
    reason = "正常" if should_voice else "重复播报"

    voice_text = ""
    if should_voice:
        unit = f"{class_name}正在放学"
        voice_text = "，".join([unit] * max(1, broadcast_count))

    last_push = api_push_history.get(card_id)
    should_push_api = (
        api_available
        and class_id
        and not test_mode
        and (last_push is None or (now - last_push).total_seconds() > deduplication_interval_seconds)
    )

    if test_mode:
        reason += "/测试模式"
    elif api_available and not should_push_api and last_push is not None:
        reason += "/推送冷却"
    elif not api_available:
        reason += "/无API服务"

    return SwipeDecision(
        should_voice=should_voice,
        voice_text=voice_text,
        should_push_api=should_push_api,
        action=action,
        reason=reason,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_udp_parser tests.test_broadcast_policy -v
```

Expected: all tests `PASS`.

- [ ] **Step 5: Integrate the new modules into the services**

```python
# src/services/config_manager.py
DEFAULT_CONFIG = {
    "udp_port": 39169,
    "time_window_start": "16:30",
    "time_window_end": "18:30",
    "broadcast_count": 3,
    "deduplication_interval_seconds": 300,
    "test_mode": False,
    "maintenance_pin": "2580",
    "maintenance_timeout_seconds": 300,
}
```

```python
# src/services/udp_server.py
from .udp_parser import parse_udp_packet
from .system_status import AlertLevel, ServiceState

...
self.status_store = status_store
...
if self.socket.bind(QHostAddress.SpecialAddress.Any, self.port):
    self.status_store.update("udp", ServiceState.ok("udp", "UDP监听正常", datetime.datetime.now()))
else:
    self.status_store.update(
        "udp",
        ServiceState(
            name="udp",
            level=AlertLevel.CRITICAL,
            summary="UDP监听中断",
            detail=f"端口 {self.port} 绑定失败",
            updated_at=datetime.datetime.now(),
        ),
    )
...
parsed = parse_udp_packet(datagram)
seq_id = parsed.sequence_id
card_id_str = parsed.card_id
```

```python
# src/services/broadcast_manager.py
from .broadcast_policy import evaluate_swipe
from .dismissal_window import format_window_label, get_active_window_signature, is_now_within_window
from .system_status import AlertLevel, ServiceState

...
decision = evaluate_swipe(
    class_name=class_name,
    class_id=class_id,
    card_id=card_id,
    window_signature=window_sig,
    voice_history=self.voice_history,
    api_push_history=self.api_push_history,
    now=datetime.datetime.now(),
    deduplication_interval_seconds=self.config.get("deduplication_interval_seconds", 300),
    broadcast_count=self.config.get("broadcast_count", 3),
    test_mode=self.config.get("test_mode", False),
    api_available=bool(self.api_service),
)
if decision.should_voice:
    self.tts_worker.add_text(decision.voice_text)
    self.voice_history[class_name] = window_sig
...
self.status_store.update("tts", ServiceState.ok("tts", "语音播报正常", datetime.datetime.now()))
```

```python
# src/services/data_sync_service.py
from .system_status import AlertLevel, ServiceState

...
try:
    self.sync_classes()
    self.sync_schedule()
    self.status_store.update("sync", ServiceState.ok("sync", "同步正常", time_now))
except Exception as exc:
    self.status_store.update(
        "sync",
        ServiceState(
            name="sync",
            level=AlertLevel.WARNING,
            summary="同步异常",
            detail=str(exc),
            updated_at=time_now,
        ),
    )
```

- [ ] **Step 6: Run the service tests together**

Run:

```bash
python3 -m unittest tests.test_dismissal_window tests.test_system_status tests.test_udp_parser tests.test_broadcast_policy -v
```

Expected: all tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_udp_parser.py tests/test_broadcast_policy.py src/services/udp_parser.py src/services/broadcast_policy.py src/services/config_manager.py src/services/udp_server.py src/services/broadcast_manager.py src/services/data_sync_service.py
git commit -m "refactor: extract packet parsing and broadcast policy"
```

### Task 3: Add maintenance-session and dashboard presentation logic

**Files:**
- Create: `tests/test_maintenance_session.py`
- Create: `tests/test_dashboard_presenter.py`
- Create: `src/ui/maintenance_session.py`
- Create: `src/ui/dashboard_presenter.py`

- [ ] **Step 1: Write the failing tests for maintenance unlock and alert presentation**

```python
# tests/test_maintenance_session.py
import datetime
import unittest

from src.ui.maintenance_session import MaintenanceSessionController


class MaintenanceSessionControllerTests(unittest.TestCase):
    def test_valid_pin_unlocks_session_until_deadline(self):
        controller = MaintenanceSessionController(pin="2580", timeout_seconds=300)
        now = datetime.datetime(2026, 4, 21, 16, 45)

        self.assertTrue(controller.unlock("2580", now))
        self.assertTrue(controller.is_unlocked(now + datetime.timedelta(seconds=10)))

    def test_session_relocks_after_timeout(self):
        controller = MaintenanceSessionController(pin="2580", timeout_seconds=60)
        now = datetime.datetime(2026, 4, 21, 16, 45)

        controller.unlock("2580", now)

        self.assertFalse(controller.is_unlocked(now + datetime.timedelta(seconds=61)))


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_dashboard_presenter.py
import datetime
import unittest

from src.services.system_status import AlertLevel, RuntimeStatusStore, ServiceState
from src.ui.dashboard_presenter import DashboardPresenter


class DashboardPresenterTests(unittest.TestCase):
    def test_critical_snapshot_becomes_pulsing_banner(self):
        store = RuntimeStatusStore()
        now = datetime.datetime(2026, 4, 21, 16, 45)
        store.update(
            "udp",
            ServiceState(
                name="udp",
                level=AlertLevel.CRITICAL,
                summary="UDP监听中断",
                detail="端口绑定失败",
                updated_at=now,
            ),
        )

        view_model = DashboardPresenter().build(store.snapshot(now), online_devices=2, window_label="今日: 16:30-17:10")

        self.assertEqual(view_model.banner_text, "UDP监听中断")
        self.assertTrue(view_model.should_pulse)
        self.assertEqual(view_model.online_devices_text, "2 台在线")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_maintenance_session tests.test_dashboard_presenter -v
```

Expected: `ModuleNotFoundError` for `src.ui.maintenance_session` and `src.ui.dashboard_presenter`.

- [ ] **Step 3: Write the minimal controller and presenter**

```python
# src/ui/maintenance_session.py
from __future__ import annotations

import datetime as dt


class MaintenanceSessionController:
    def __init__(self, pin: str, timeout_seconds: int):
        self.pin = pin
        self.timeout_seconds = timeout_seconds
        self.deadline: dt.datetime | None = None

    def unlock(self, attempt: str, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now()
        if attempt != self.pin:
            self.deadline = None
            return False
        self.deadline = now + dt.timedelta(seconds=self.timeout_seconds)
        return True

    def touch(self, now: dt.datetime | None = None) -> None:
        now = now or dt.datetime.now()
        if self.deadline is not None:
            self.deadline = now + dt.timedelta(seconds=self.timeout_seconds)

    def is_unlocked(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now()
        return self.deadline is not None and now <= self.deadline
```

```python
# src/ui/dashboard_presenter.py
from __future__ import annotations

import dataclasses

from src.services.system_status import AlertLevel, DashboardSnapshot


@dataclasses.dataclass(frozen=True)
class DashboardViewModel:
    banner_text: str
    should_pulse: bool
    online_devices_text: str
    window_label: str
    overall_level: AlertLevel


class DashboardPresenter:
    def build(self, snapshot: DashboardSnapshot, online_devices: int, window_label: str) -> DashboardViewModel:
        return DashboardViewModel(
            banner_text=snapshot.primary_alert,
            should_pulse=snapshot.should_pulse,
            online_devices_text=f"{online_devices} 台在线",
            window_label=window_label,
            overall_level=snapshot.overall_level,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_maintenance_session tests.test_dashboard_presenter -v
```

Expected: all tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_maintenance_session.py tests/test_dashboard_presenter.py src/ui/maintenance_session.py src/ui/dashboard_presenter.py
git commit -m "feat: add maintenance session and dashboard presenter"
```

### Task 4: Rebuild the main window into guard dashboard + protected maintenance mode

**Files:**
- Create: `tests/test_main_window_smoke.py`
- Create: `src/ui/dashboard_view.py`
- Create: `src/ui/maintenance_panel.py`
- Modify: `src/ui/main_window.py`
- Modify: `src/ui/settings_dialog.py`
- Modify: `src/ui/device_manager_dialog.py`
- Modify: `src/ui/schedule_dialog.py`
- Modify: `src/ui/mapping_dialog.py`
- Modify: `main.py`

- [ ] **Step 1: Write the failing smoke test for the new window shell**

```python
# tests/test_main_window_smoke.py
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


class FakeConfig:
    def __init__(self):
        self.values = {
            "time_window_start": "16:30",
            "time_window_end": "18:30",
            "test_mode": False,
            "maintenance_pin": "2580",
            "maintenance_timeout_seconds": 300,
            "schedules": [],
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        return None


class FakeDb:
    def get_recent_logs(self):
        return []

    def get_devices(self):
        return []


class FakeBroadcastManager(QObject):
    log_updated = pyqtSignal(str, str, str, str, str)

    def is_within_time_window(self):
        return False


class FakeUdpServer(QObject):
    card_swiped = pyqtSignal(str, str)
    device_updated = pyqtSignal(str, str, str, str)


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_guard_mode_is_default_and_maintenance_panel_is_hidden(self):
        window = MainWindow(FakeConfig(), FakeDb(), FakeBroadcastManager(), FakeUdpServer(), None)
        self.assertEqual(window.current_mode, "guard")
        self.assertTrue(window.dashboard_view.isVisible())
        self.assertFalse(window.maintenance_panel.isVisible())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_main_window_smoke -v
```

Expected: failure because `MainWindow` does not yet expose `current_mode`, `dashboard_view`, or `maintenance_panel`.

- [ ] **Step 3: Implement the dashboard and maintenance widgets**

```python
# src/ui/dashboard_view.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QTableWidget, QVBoxLayout, QWidget


class DashboardView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.banner = QLabel("系统初始化中")
        self.banner.setObjectName("statusBanner")
        layout.addWidget(self.banner)

        summary_grid = QGridLayout()
        self.runtime_card = QLabel("运行状态")
        self.device_card = QLabel("0 台在线")
        self.window_card = QLabel("默认: 16:30 - 18:30")
        summary_grid.addWidget(self.runtime_card, 0, 0)
        summary_grid.addWidget(self.device_card, 0, 1)
        summary_grid.addWidget(self.window_card, 0, 2)
        layout.addLayout(summary_grid)

        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["时间", "卡号", "班级", "动作", "详细原因"])
        layout.addWidget(self.log_table)
```

```python
# src/ui/maintenance_panel.py
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class MaintenancePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.school_button = QPushButton("绑定学校")
        self.schedule_button = QPushButton("放学时间配置")
        self.device_button = QPushButton("设备管理")
        self.mapping_button = QPushButton("卡号管理")
        self.sync_button = QPushButton("立即同步")
        for button in (
            self.school_button,
            self.schedule_button,
            self.device_button,
            self.mapping_button,
            self.sync_button,
        ):
            layout.addWidget(button)
        layout.addStretch()
```

```python
# src/ui/main_window.py
from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtWidgets import QInputDialog, QMainWindow, QMessageBox, QStackedWidget, QWidget, QVBoxLayout

from src.services.dismissal_window import format_window_label
from .dashboard_presenter import DashboardPresenter
from .dashboard_view import DashboardView
from .maintenance_panel import MaintenancePanel
from .maintenance_session import MaintenanceSessionController

...
self.current_mode = "guard"
self.presenter = DashboardPresenter()
self.maintenance_session = MaintenanceSessionController(
    pin=self.config.get("maintenance_pin", "2580"),
    timeout_seconds=self.config.get("maintenance_timeout_seconds", 300),
)
self.mode_stack = QStackedWidget()
self.dashboard_view = DashboardView(self)
self.maintenance_panel = MaintenancePanel(self)
self.mode_stack.addWidget(self.dashboard_view)
self.mode_stack.addWidget(self.maintenance_panel)
...
def enter_guard_mode(self):
    self.current_mode = "guard"
    self.mode_stack.setCurrentWidget(self.dashboard_view)
    self.maintenance_panel.hide()
    self.dashboard_view.show()

def enter_maintenance_mode(self):
    self.current_mode = "maintenance"
    self.mode_stack.setCurrentWidget(self.maintenance_panel)
    self.dashboard_view.hide()
    self.maintenance_panel.show()

def request_maintenance_mode(self):
    pin, ok = QInputDialog.getText(self, "维护模式", "请输入4位维护码：")
    if ok and self.maintenance_session.unlock(pin):
        self.enter_maintenance_mode()
    elif ok:
        QMessageBox.warning(self, "错误", "维护码错误")
```

- [ ] **Step 4: Wire the maintenance actions and modernize the dialogs**

```python
# src/ui/main_window.py
from PyQt6.QtCore import QRect

self.maintenance_panel.school_button.clicked.connect(self.open_settings_dialog)
self.maintenance_panel.schedule_button.clicked.connect(self.open_schedule_dialog)
self.maintenance_panel.device_button.clicked.connect(self.open_device_manager)
self.maintenance_panel.mapping_button.clicked.connect(self.open_mapping_dialog)
self.maintenance_panel.sync_button.clicked.connect(self.data_sync_service.force_sync if self.data_sync_service else lambda: None)

def keyPressEvent(self, event):
    if event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_M:
        self.request_maintenance_mode()
        return
    super().keyPressEvent(event)

def mouseDoubleClickEvent(self, event):
    hotspot = QRect(self.width() - 80, 0, 80, 80)
    if hotspot.contains(event.pos()):
        self.request_maintenance_mode()
        return
    super().mouseDoubleClickEvent(event)
```

```python
# src/ui/settings_dialog.py
self.setStyleSheet("QDialog { background: #111827; color: #e5eefb; } QPushButton { min-height: 36px; }")
```

```python
# main.py
window = MainWindow(config_manager, db_manager, broadcast_manager, udp_server, data_sync_service)
window.enter_guard_mode()
window.showMaximized()
```

- [ ] **Step 5: Run the smoke test to verify the new shell**

Run:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_main_window_smoke -v
```

Expected: test `PASS`.

- [ ] **Step 6: Run the broader local verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 -m compileall main.py src tests
```

Expected: all tests `PASS`, and `compileall` completes without syntax errors.

- [ ] **Step 7: Commit**

```bash
git add tests/test_main_window_smoke.py src/ui/dashboard_view.py src/ui/maintenance_panel.py src/ui/main_window.py src/ui/settings_dialog.py src/ui/device_manager_dialog.py src/ui/schedule_dialog.py src/ui/mapping_dialog.py main.py
git commit -m "feat: rebuild main window as guarded dashboard"
```

### Task 5: Finish packaging and operator documentation

**Files:**
- Modify: `build_exe.py`
- Modify: `README.md`

- [ ] **Step 1: Add a failing packaging/documentation sanity check**

```python
# This is a manual failing check recorded before edits:
# 1. README does not mention guard mode / maintenance mode.
# 2. build_exe.py does not mention the Windows dashboard packaging target.
#
# Capture the current state:
```

Run:

```bash
rg -n "维护模式|值守看板|guard mode|maintenance mode" README.md build_exe.py
```

Expected: no matches.

- [ ] **Step 2: Update the packaging script and README**

```python
# build_exe.py
args = [
    "main.py",
    "--name=SchoolDismissalSystem",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onefile",
    "--hidden-import=sqlite3",
    "--hidden-import=pyttsx3.drivers",
    "--hidden-import=pyttsx3.drivers.sapi5",
    "--hidden-import=requests",
]
print("Building Windows guard-dashboard client...")
```

```markdown
<!-- README.md -->
## 值守模式与维护模式

- 默认启动进入值守看板模式，适合 1920×1080 横屏长期值守
- 维护模式默认隐藏，按 `Ctrl+Shift+M` 或双击右上角隐藏区域后输入 4 位维护码进入
- 维护模式 5 分钟无操作会自动回退到值守看板
```

- [ ] **Step 3: Run the sanity check again**

Run:

```bash
rg -n "维护模式|值守看板|guard mode|maintenance mode" README.md build_exe.py
```

Expected: matches in both files.

- [ ] **Step 4: Commit**

```bash
git add build_exe.py README.md
git commit -m "docs: document guard dashboard operations"
```

## Final Verification Checklist

- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_main_window_smoke -v`
- [ ] `python3 -m compileall main.py src tests`
- [ ] On Windows, launch the packaged app and verify:
  - [ ] starts maximized into guard mode
  - [ ] hidden maintenance entry works
  - [ ] maintenance auto-lock works after inactivity
  - [ ] UDP health, sync health, and TTS health surface in the dashboard
  - [ ] critical alerts visibly pulse without adding heavy runtime overhead
