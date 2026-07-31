try:
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread
except ImportError:
    class QObject:
        def __init__(self, *args, **kwargs):
            pass

        def moveToThread(self, thread):
            pass

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def emit(self, *args, **kwargs):
            for callback in self._callbacks:
                callback(*args, **kwargs)

    def pyqtSignal(*args, **kwargs):
        return _Signal()

    class QTimer:
        def __init__(self, *args, **kwargs):
            self.timeout = _Signal()

        def setSingleShot(self, single_shot):
            self.single_shot = single_shot

        def start(self, interval):
            self.interval = interval

        def stop(self):
            pass

    class QThread:
        def __init__(self):
            self.started = _Signal()

        def start(self):
            self.started.emit()

        def quit(self):
            pass

        def wait(self):
            pass

import datetime

from .pre_window_sync import get_next_pre_window_sync_time
from .dismissal_window import is_now_within_window


class DataSyncWorker(QObject):
    finished = pyqtSignal()
    
    def __init__(self, api_service, db_manager, config_manager, clock=None, led_service=None):
        super().__init__()
        self.api = api_service
        self.db = db_manager
        self.config = config_manager
        self.clock = clock or datetime.datetime.now
        self.led_service = led_service
        self.running = True

    def run(self):
        self.pre_window_timer = QTimer(self)
        self.pre_window_timer.setSingleShot(True)
        self.pre_window_timer.timeout.connect(self._handle_pre_window_sync)

        # Initial sync on start
        self.sync_all()
        
        # Use QTimer for periodic sync (non-blocking) to allow signals (force_sync) to work
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_all)
        self.timer.start(30 * 60 * 1000) # 30 minutes in ms

    def sync_all(self):
        if not self.api.school_id:
            print("[Sync] Skipping sync: School ID not set.")
            return

        print("[Sync] Starting data sync...")
        self.sync_classes(clear_existing=True)
        self.sync_schedule()
        if self.led_service:
            active = is_now_within_window(
                self.config.get("schedules"),
                self.config.get("time_window_start", "16:30"),
                self.config.get("time_window_end", "18:30"),
                now=self.clock(),
                class_type=1,
            ) or bool(self.config.get("test_mode", False))
            transition_refresh = self.led_service.set_dismissal_active(active)
            if active and not transition_refresh:
                self.led_service.refresh_async()
        print("[Sync] Data sync completed.")
        self.schedule_pre_window_sync()

    def sync_classes(self, clear_existing=False):
        classes = self.api.get_classes()
        if classes is None:
            print("[Sync] Class request failed; keeping the previous class data.")
            return
        if clear_existing and hasattr(self.db, "clear_mappings"):
            self.db.clear_mappings()
        count = 0
        saved_class_ids = set()
        for source_order, cls in enumerate(classes):
            card_id_raw = cls.get("cardId")
            class_name = cls.get("classVoiceName") or cls.get("className")
            class_id = cls.get("classId")
            class_type = cls.get("classType")
            class_show_name = cls.get("classShowName")
            class_voice_name = cls.get("classVoiceName")
            grade_name = cls.get("gradeName")
            try:
                normalized_class_type = int(class_type)
            except (TypeError, ValueError):
                normalized_class_type = 0

            # LED catalog is class-based rather than card-based. Keep only
            # classes actually returned by the service and deduplicate classId.
            catalog_key = (str(normalized_class_type), str(class_id))
            if (
                normalized_class_type == 1
                and class_id
                and class_name
                and catalog_key not in saved_class_ids
                and hasattr(self.db, "upsert_led_class")
            ):
                self.db.upsert_led_class(
                    school_id=self.api.school_id,
                    class_type=normalized_class_type,
                    class_id=class_id,
                    grade_name=grade_name,
                    class_name=class_name,
                    class_show_name=class_show_name,
                    class_voice_name=class_voice_name,
                    source_order=source_order,
                )
                saved_class_ids.add(catalog_key)

            if card_id_raw and class_name:
                if isinstance(card_id_raw, list):
                    cards = card_id_raw
                elif isinstance(card_id_raw, str):
                    cards = card_id_raw.split(",")
                else:
                    cards = [str(card_id_raw)]

                for c_id in cards:
                    clean_card_id = str(c_id).strip()
                    if not clean_card_id:
                        continue
                    self.db.add_mapping(
                        clean_card_id,
                        class_name,
                        class_id,
                        school_id=self.api.school_id,
                        class_type=class_type,
                        class_show_name=class_show_name,
                        class_voice_name=class_voice_name,
                    )
                    count += 1
        print(f"[Sync] Synced {count} card mappings.")

    def sync_schedule(self):
        schedules = self.api.get_school_dismissal_schedule()
        if schedules is not None:
            # schedules is a list of dicts:
            # [{"weekday": 1, "timeRanges": [{"startTime": "15:30", "endTime": "16:00"}]}, ...]
            self.config.set("schedules", schedules)
            self.config.save()
            print(f"[Sync] Schedule fetched and saved: {len(schedules)} rules.")
        else:
            print("[Sync] Schedule request failed; keeping the previous schedule.")

    def schedule_pre_window_sync(self):
        if not hasattr(self, "pre_window_timer"):
            return

        self.pre_window_timer.stop()
        now = self.clock()
        trigger_time = get_next_pre_window_sync_time(
            self.config.get("schedules", []),
            now=now,
            lead_minutes=2,
        )
        if trigger_time is None:
            print("[Sync] No upcoming dismissal window pre-sync scheduled.")
            return

        delay_ms = max(1, int((trigger_time - now).total_seconds() * 1000))
        self.pre_window_timer.start(delay_ms)
        print(f"[Sync] Next pre-window sync scheduled for {trigger_time:%Y-%m-%d %H:%M:%S}.")

    def _handle_pre_window_sync(self):
        print("[Sync] Running pre-window data sync.")
        self.sync_all()

    def stop_timer(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, "pre_window_timer"):
            self.pre_window_timer.stop()
        self.running = False

class DataSyncService(QObject):
    force_sync_signal = pyqtSignal()
    stop_signal = pyqtSignal()

    def __init__(self, api_service, db_manager, config_manager, led_service=None):
        super().__init__()
        self.thread = QThread()
        self.worker = DataSyncWorker(
            api_service,
            db_manager,
            config_manager,
            led_service=led_service,
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

    @property
    def db(self):
        return self.worker.db
        
    def force_sync(self):
        self.force_sync_signal.emit()
