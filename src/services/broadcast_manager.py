from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import pyttsx3
import datetime
import time
import queue
import os

from .broadcast_policy import evaluate_swipe
from .dismissal_window import get_active_window_signature
from .system_status import AlertLevel, RuntimeStatusStore, ServiceState

class TTSWorker(QObject):
    finished = pyqtSignal()
    
    def __init__(self):
        super().__init__()
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
                if not self.queue.empty():
                    text = self.queue.get()
                    print(f"[TTS] Broadcasting: {text}")
                    
                    try:
                        # Re-init engine for each broadcast to prevent SAPI state issues
                        engine = pyttsx3.init()
                        engine.setProperty('volume', 1.0)
                        engine.say(text)
                        
                        # Use runAndWait to block until finished
                        engine.runAndWait()
                        
                        # Cleanup engine explicitly
                        engine.stop()
                        del engine
                    except Exception as e_inner:
                         print(f"[TTS] Inner Loop Error: {e_inner}")

                    time.sleep(0.5) 
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"[TTS] Playback Error: {e}")
                time.sleep(1)
        
        # Cleanup COM in the WORKER THREAD
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except:
            pass

    def stop(self):
        self.running = False
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
        self.tts_worker = TTSWorker()
        self.tts_worker.moveToThread(self.tts_thread)
        self.tts_thread.started.connect(self.tts_worker.run)
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
        now = datetime.datetime.now()

        # 1. Lookup Class (FIRST)
        class_info = self.db.get_class_info_by_card(card_id)
        class_name = class_info[0]
        class_id = class_info[1]
        window_sig = self.get_current_window_signature(now=now)
        if window_sig:
            print(f"[Debug] Current Window: {window_sig}")

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

        if decision.should_voice and class_name:
            self.tts_worker.add_text(decision.voice_text)
            self.voice_history[class_name] = window_sig or ""

        if decision.should_push_api and self.api_service and class_id:
            import threading

            def push_api():
                print(f"[Debug] Spawning API Push Thread for Class {class_id}")
                self.api_service.push_dismissal_notice(class_id, card_id, 1)

            threading.Thread(target=push_api, daemon=True).start()
            self.api_push_history[card_id] = now

        # Log Result
        print(f"[Debug] Process Result: {decision.action} - {decision.reason}")
        self._log_event(card_id, class_name or "未知", decision.action, decision.reason)

        if decision.action == "跳过" and decision.reason == "无效卡号":
            self._set_status(AlertLevel.WARNING, "invalid card", card_id)
        else:
            self._set_status(AlertLevel.OK, "swipe processed", decision.action)

    def is_within_time_window(self):
        return self.get_current_window_signature() is not None

    def _log_event(self, card_id, class_name, action, reason):
        # DB: Combine for backward compatibility
        full_status = f"{action} ({reason})" if reason else action
        self.db.log_swipe(card_id, class_name, full_status)
        
        now = datetime.datetime.now()
        now_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        # Emit Signal for UI
        self.log_updated.emit(now_str, card_id, class_name, action, reason)
        
        # File Logging
        try:
            log_file = os.path.join(self.log_dir, f"{date_str}.txt")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] [Card:{card_id}] [Class:{class_name}] [{action}] [{reason}]\n")
        except Exception as e:
            print(f"[Log] File Write Error: {e}")

    def cleanup(self):
        self.tts_worker.stop()
        self.tts_thread.quit()
        self.tts_thread.wait()
