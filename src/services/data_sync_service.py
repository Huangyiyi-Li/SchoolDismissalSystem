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

class DataSyncWorker(QObject):
    finished = pyqtSignal()
    
    def __init__(self, api_service, db_manager, config_manager):
        super().__init__()
        self.api = api_service
        self.db = db_manager
        self.config = config_manager
        self.running = True

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
            return

        print("[Sync] Starting data sync...")
        self.sync_classes()
        self.sync_schedule()
        print("[Sync] Data sync completed.")

    def sync_classes(self):
        classes = self.api.get_classes()
        if classes:
            count = 0
            for cls in classes:
                # cls: {classId, cardId, classVoiceName, ...}
                # Note: cardId in document says "Array" or String?
                # Example: "cardId": "1". If it handles list, we iterate.
                # Assuming simple relation for now as per previous logic.
                
                card_id_raw = cls.get("cardId")
                # Fallback to className if classVoiceName is missing
                class_name = cls.get("classVoiceName") or cls.get("className")
                class_id = cls.get("classId")
                class_type = cls.get("classType")
                class_show_name = cls.get("classShowName")
                class_voice_name = cls.get("classVoiceName")
                
                if card_id_raw and class_name:
                    # If card_id_raw is comma separated or list?
                    cards = []
                    if isinstance(card_id_raw, list):
                        cards = card_id_raw
                    elif isinstance(card_id_raw, str):
                        cards = card_id_raw.split(',') # Just in case
                    else:
                        cards = [str(card_id_raw)]
                        
                    for c_id in cards:
                        clean_card_id = str(c_id).strip()
                        if not clean_card_id:
                            continue
                        # Pass school_id (from API Service config) to DB
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
        if schedules:
            # schedules is a list of dicts:
            # [{"weekday": 1, "timeRanges": [{"startTime": "15:30", "endTime": "16:00"}]}, ...]
            self.config.set("schedules", schedules)
            self.config.save()
            print(f"[Sync] Schedule fetched and saved: {len(schedules)} rules.")
        else:
            print("[Sync] No schedule returned from API or error occurred.")

    def stop_timer(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
        self.running = False

class DataSyncService(QObject):
    force_sync_signal = pyqtSignal()
    stop_signal = pyqtSignal()

    def __init__(self, api_service, db_manager, config_manager):
        super().__init__()
        self.thread = QThread()
        self.worker = DataSyncWorker(api_service, db_manager, config_manager)
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
