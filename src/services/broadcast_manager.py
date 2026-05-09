from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import pyttsx3
import datetime
import time
import queue
import os
import logging

from .broadcast_policy import evaluate_swipe
from .dismissal_window import get_active_window_signature
from .system_status import AlertLevel, RuntimeStatusStore, ServiceState
from .tts_settings import normalize_tts_rate, normalize_tts_volume

class TTSWorker(QObject):
    finished = pyqtSignal()
    spoken = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, config_manager=None):
        super().__init__()
        self.config = config_manager
        self.queue = queue.Queue()
        self.retry_count = 3
        self.running = True

    def add_text(self, text):
        self.queue.put(text)

    def run(self):
        # Windows/PyQt6 thread compatibility fix for SAPI5
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass 

        while self.running:
            try:
                try:
                    text = self.queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if text is None:
                    continue

                print(f"[TTS] Broadcasting: {text}")

                try:
                    engine = pyttsx3.init()
                    rate = normalize_tts_rate(
                        self.config.get("tts_rate", 160) if self.config else 160
                    )
                    volume = normalize_tts_volume(
                        self.config.get("tts_volume", 1.0) if self.config else 1.0
                    )
                    engine.setProperty("rate", rate)
                    engine.setProperty("volume", volume)
                    logging.getLogger(__name__).info(
                        "TTS speak start rate=%s volume=%.2f text=%s",
                        rate,
                        volume,
                        text,
                    )
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                    del engine
                    self.spoken.emit(text)
                except Exception as e_inner:
                    logging.getLogger(__name__).exception("TTS playback failed")
                    self.error.emit(str(e_inner))

                time.sleep(0.5)
            except Exception as e:
                logging.getLogger(__name__).exception("TTS worker loop failed")
                self.error.emit(str(e))
                time.sleep(1)
        
        # Cleanup COM in the WORKER THREAD
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except:
            pass

    def stop(self):
        self.running = False
        self.queue.put(None)
        # Do NOT uninitialize COM here, as this runs in Main Thread!


class BroadcastManager(QObject):
    log_updated = pyqtSignal(str, str, str, str, str) # time, card, class, action, reason
    queue_updated = pyqtSignal(list) # list of class names

    def __init__(self, config_manager, db_manager, api_service=None, status_store=None):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.api_service = api_service
        self.status_store = status_store or RuntimeStatusStore()
        
        # Ensure logs directory exists
        from ..utils.path_utils import get_app_root
        self.log_dir = os.path.join(get_app_root(), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Deduplication state
        self.voice_history = {}
        self.api_push_history = {}
        
        # TTS Thread
        self.tts_thread = QThread()
        self.tts_worker = TTSWorker(config_manager)
        self.tts_worker.moveToThread(self.tts_thread)
        self.tts_thread.started.connect(self.tts_worker.run)
        self.tts_worker.spoken.connect(self._handle_tts_success)
        self.tts_worker.error.connect(self._handle_tts_error)
        self.tts_thread.start()
        self._set_status(AlertLevel.OK, "broadcast ready")

    def _set_status(self, level, summary, detail=""):
        now = datetime.datetime.now()
        self.status_store.update(
            "broadcast",
            ServiceState(
                name="broadcast",
                level=level,
                summary=summary,
                detail=detail,
                updated_at=now,
            ),
        )

    def get_current_window_signature(self, now=None):
        return get_active_window_signature(
            self.config.get("schedules"),
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
            now=now,
        )

    def process_swipe(self, card_id, ip):
        started = time.perf_counter()
        now = datetime.datetime.now()

        # 1. Lookup Class (FIRST)
        lookup_started = time.perf_counter()
        class_info = self.db.get_class_info_by_card(card_id)
        lookup_finished = time.perf_counter()
        class_name = class_info[0]
        class_id = class_info[1]
        window_sig = self.get_current_window_signature(now=now)
        if window_sig:
            print(f"[Debug] Current Window: {window_sig}")

        decision_started = time.perf_counter()
        decision = evaluate_swipe(
            class_name=class_name,
            class_id=class_id,
            card_id=card_id,
            window_signature=window_sig,
            now=now,
            voice_history=self.voice_history,
            api_push_history=self.api_push_history,
            deduplication_interval_seconds=self.config.get("deduplication_interval_seconds", 300),
            broadcast_count=self.config.get("broadcast_count", 3),
            test_mode=self.config.get("test_mode", False),
            api_service_available=self.api_service is not None,
        )
        decision_finished = time.perf_counter()

        tts_queue_ms = 0.0
        if decision.should_voice and class_name:
            tts_started = time.perf_counter()
            self.tts_worker.add_text(decision.voice_text)
            self.voice_history[class_name] = window_sig or ""
            tts_queue_ms = (time.perf_counter() - tts_started) * 1000.0

        api_dispatch_ms = 0.0
        if decision.should_push_api and self.api_service and class_id:
            import threading

            def push_api():
                print(f"[Debug] Spawning API Push Thread for Class {class_id}")
                self.api_service.push_dismissal_notice(class_id, card_id, 1)

            api_started = time.perf_counter()
            threading.Thread(target=push_api, daemon=True).start()
            self.api_push_history[card_id] = now
            api_dispatch_ms = (time.perf_counter() - api_started) * 1000.0

        # Log Result
        print(f"[Debug] Process Result: {decision.action} - {decision.reason}")
        log_started = time.perf_counter()
        self._log_event(card_id, class_name or "未知", decision.action, decision.reason)
        log_ms = (time.perf_counter() - log_started) * 1000.0

        if decision.action == "跳过" and decision.reason == "无效卡号":
            self._set_status(AlertLevel.WARNING, "invalid card", card_id)
        else:
            self._set_status(AlertLevel.OK, "swipe processed", decision.action)
        logging.getLogger(__name__).info(
            "Swipe pipeline ip=%s card_id=%s class=%s lookup_ms=%.1f decision_ms=%.1f tts_queue_ms=%.1f api_dispatch_ms=%.1f log_ms=%.1f total_ms=%.1f action=%s reason=%s",
            ip,
            card_id,
            class_name or "未知",
            (lookup_finished - lookup_started) * 1000.0,
            (decision_finished - decision_started) * 1000.0,
            tts_queue_ms,
            api_dispatch_ms,
            log_ms,
            (time.perf_counter() - started) * 1000.0,
            decision.action,
            decision.reason,
        )

    @pyqtSlot(str)
    def _handle_tts_success(self, text):
        logging.getLogger(__name__).info("TTS playback finished")
        self._set_status(AlertLevel.OK, "tts ok", text[:32])

    @pyqtSlot(str)
    def _handle_tts_error(self, detail):
        self._set_status(AlertLevel.WARNING, "tts failed", detail)

    def is_within_time_window(self):
        return self.get_current_window_signature() is not None

    def _log_event(self, card_id, class_name, action, reason):
        started = time.perf_counter()
        # DB: Combine for backward compatibility
        full_status = f"{action} ({reason})" if reason else action
        db_started = time.perf_counter()
        self.db.log_swipe(card_id, class_name, full_status)
        db_ms = (time.perf_counter() - db_started) * 1000.0
        
        now = datetime.datetime.now()
        now_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        # Emit Signal for UI
        ui_started = time.perf_counter()
        self.log_updated.emit(now_str, card_id, class_name, action, reason)
        ui_ms = (time.perf_counter() - ui_started) * 1000.0
        
        # File Logging
        file_ms = 0.0
        try:
            file_started = time.perf_counter()
            log_file = os.path.join(self.log_dir, f"{date_str}.txt")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] [Card:{card_id}] [Class:{class_name}] [{action}] [{reason}]\n")
            file_ms = (time.perf_counter() - file_started) * 1000.0
        except Exception as e:
            print(f"[Log] File Write Error: {e}")
        logging.getLogger(__name__).info(
            "Swipe log persisted card_id=%s class=%s db_ms=%.1f ui_emit_ms=%.1f file_ms=%.1f total_ms=%.1f",
            card_id,
            class_name,
            db_ms,
            ui_ms,
            file_ms,
            (time.perf_counter() - started) * 1000.0,
        )

    def cleanup(self):
        self.tts_worker.stop()
        self.tts_thread.quit()
        self.tts_thread.wait()
