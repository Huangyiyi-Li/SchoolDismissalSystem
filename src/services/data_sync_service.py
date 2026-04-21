try:
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread
except ModuleNotFoundError:  # pragma: no cover - exercised only in headless test envs
    class _DummySignal:
        def connect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    def pyqtSignal(*args, **kwargs):
        return _DummySignal()

    class QObject:
        def __init__(self, *args, **kwargs):
            pass

    class QTimer:
        def __init__(self, *args, **kwargs):
            self.timeout = _DummySignal()

        def start(self, *args, **kwargs):
            return None

        def stop(self):
            return None

    class QThread:
        def __init__(self, *args, **kwargs):
            self.started = _DummySignal()

        def start(self):
            return None

        def quit(self):
            return None

        def wait(self):
            return None
import time
import datetime

from .system_status import AlertLevel, RuntimeStatusStore, ServiceState


def _normalize_card_ids(card_id_raw):
    if card_id_raw is None:
        return []

    if isinstance(card_id_raw, list):
        raw_items = card_id_raw
    elif isinstance(card_id_raw, str):
        raw_items = card_id_raw.split(",")
    else:
        raw_items = [str(card_id_raw)]

    result = []
    for item in raw_items:
        if item is None:
            continue
        token = str(item).strip()
        if token:
            result.append(token)
    return result

class DataSyncWorker(QObject):
    finished = pyqtSignal()
    
    def __init__(self, api_service, db_manager, config_manager, status_store=None):
        super().__init__()
        self.api = api_service
        self.db = db_manager
        self.config = config_manager
        self.status_store = status_store or RuntimeStatusStore()
        self.running = True

    def _set_sync_status(self, level, summary, detail=""):
        now = datetime.datetime.now()
        self.status_store.update(
            "sync",
            ServiceState(
                name="sync",
                level=level,
                summary=summary,
                detail=detail,
                updated_at=now,
            ),
        )

    def run(self):
        # Initial sync on start
        self.sync_all()
        
        # Use QTimer for periodic sync (non-blocking) to allow signals (force_sync) to work
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_all)
        self.timer.start(30 * 60 * 1000) # 30 minutes in ms

    def sync_all(self):
        if not self.api.school_id:
            print("[Sync] Skipping sync: School ID not set.")
            self._set_sync_status(AlertLevel.WARNING, "sync skipped", "school id not set")
            return

        print("[Sync] Starting data sync...")
        classes_ok = self.sync_classes()
        schedule_ok = self.sync_schedule()
        print("[Sync] Data sync completed.")
        if classes_ok and schedule_ok:
            self._set_sync_status(AlertLevel.OK, "sync completed")
        elif classes_ok or schedule_ok:
            self._set_sync_status(AlertLevel.WARNING, "sync partial")
        else:
            self._set_sync_status(AlertLevel.WARNING, "sync no updates")

    def sync_classes(self):
        classes = self.api.get_classes()
        if not classes:
            print("[Sync] No classes returned from API or error occurred.")
            return False

        count = 0
        for cls in classes:
            # cls: {classId, cardId, classVoiceName, ...}
            card_id_raw = cls.get("cardId")
            class_name = cls.get("classVoiceName") or cls.get("className")
            class_id = cls.get("classId")

            if card_id_raw and class_name:
                cards = _normalize_card_ids(card_id_raw)
                for c_id in cards:
                    self.db.add_mapping(c_id, class_name, class_id, school_id=self.api.school_id)
                    count += 1
        print(f"[Sync] Synced {count} card mappings.")
        return count > 0

    def sync_schedule(self):
        schedules = self.api.get_school_dismissal_schedule()
        if schedules:
            # schedules is a list of dicts:
            # [{"weekday": 1, "timeRanges": [{"startTime": "15:30", "endTime": "16:00"}]}, ...]
            self.config.set("schedules", schedules)
            self.config.save()
            print(f"[Sync] Schedule fetched and saved: {len(schedules)} rules.")
            return True
        else:
            print("[Sync] No schedule returned from API or error occurred.")
            return False

    def stop_timer(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
        self.running = False

class DataSyncService(QObject):
    force_sync_signal = pyqtSignal()
    stop_signal = pyqtSignal()

    def __init__(self, api_service, db_manager, config_manager, status_store=None):
        super().__init__()
        self.thread = QThread()
        self.worker = DataSyncWorker(
            api_service,
            db_manager,
            config_manager,
            status_store=status_store,
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.force_sync_signal.connect(self.worker.sync_all)
        self.stop_signal.connect(self.worker.stop_timer)
    
    def start(self):
        self.thread.start()

    def stop(self):
        # Use signal to stop timer in worker thread safely
        self.stop_signal.emit()
        self.thread.quit()
        self.thread.wait()

    @property
    def api(self):
        return self.worker.api
        
    def force_sync(self):
        self.force_sync_signal.emit()
