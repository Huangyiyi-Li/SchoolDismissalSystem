from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import pyttsx3
import datetime
import time
import queue
import os

from .voice_text import build_dismissal_voice_text
from .broadcast_mode import get_effective_window_signature
from .dismissal_window import get_active_window_signature
from .log_records import DISPLAY_TIMESTAMP_FORMAT

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
                        
                        # Broadcast 3 times
                        full_text = f"{text}，{text}，{text}"
                        engine.say(full_text)
                        
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
    log_updated = pyqtSignal(str, str, str, str, str, str) # time, source, type, name, action, reason
    queue_updated = pyqtSignal(list) # list of class names

    def __init__(self, config_manager, db_manager, api_service=None, led_service=None):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.api_service = api_service
        self.led_service = led_service
        
        # Ensure logs directory exists
        from ..utils.path_utils import get_app_root
        self.log_dir = os.path.join(get_app_root(), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Deduplication state
        self.voice_history = {}
        self.api_push_history = {}
        self.manual_command_history = set()
        
        # TTS Thread
        self.tts_thread = QThread()
        self.tts_worker = TTSWorker()
        self.tts_worker.moveToThread(self.tts_thread)
        self.tts_thread.started.connect(self.tts_worker.run)
        self.tts_thread.start()

    def get_current_window_signature(self, class_type=None):
        """
        Returns a unique string for the current active time window, e.g. 'Weekday-1_08:30-18:30'.
        Returns None if not in any window.
        """
        schedules = self.config.get("schedules")
        if not schedules and class_type == 2:
            return None
        return get_active_window_signature(
            schedules,
            self.config.get("time_window_start", "16:30"),
            self.config.get("time_window_end", "18:30"),
            class_type=class_type,
        )

    def process_swipe(self, card_id, ip):
        # 1. Lookup Class (FIRST)
        class_info = self.db.get_class_info_by_card(card_id)
        class_name = class_info[0]
        class_id = class_info[1]
        class_type = class_info[3]
        
        if not class_name:
            self._log_event(
                card_id,
                "未知",
                "跳过",
                "无效卡号",
                source="刷卡",
                source_detail=card_id,
            )
            return

        # 2. Check Time Window (SECOND)
        is_test_mode = self.config.get("test_mode", False)
        window_sig = get_effective_window_signature(
            self.get_current_window_signature(class_type=class_type),
            is_test_mode,
        )
        if not window_sig:
            self._log_event(
                card_id,
                class_name,
                "跳过",
                "非播报时段",
                class_type=class_type,
                source="刷卡",
                source_detail=card_id,
            )
            return

        print(f"[Debug] Current Window: {window_sig}")

        # 3. Voice Logic (Class Level Deduplication)
        last_window = self.voice_history.get(class_name)
        should_voice = (last_window != window_sig)
        
        action = "处理中"
        reason = ""
        
        if should_voice:
            message = build_dismissal_voice_text(class_name)
            self.tts_worker.add_text(message)
            self.voice_history[class_name] = window_sig
            action = "语音播报"
            reason = "正常"
        else:
            action = "语音跳过"
            reason = "重复播报"

        # 4. API Push Logic (Card Level Throttling)
        should_push = False
        last_push = self.api_push_history.get(card_id)
        interval = self.config.get("deduplication_interval_seconds", 300)
        
        if not last_push or (datetime.datetime.now() - last_push).total_seconds() > interval:
            should_push = True
        else:
            if "播报" in action:
                reason += "/推送冷却"
            else:
                reason = "重复/推送冷却"

        if should_push:
            # Check Test Mode
            if self.api_service and class_id and not is_test_mode:
                import threading
                def push_api():
                     print(f"[Debug] Spawning API Push Thread for Class {class_id}")
                     self.api_service.push_dismissal_notice(
                         class_id,
                         card_id,
                         dismissal_status=1,
                         class_type=class_type,
                         trigger_type=1,
                     )
                threading.Thread(target=push_api, daemon=True).start()
                self.api_push_history[card_id] = datetime.datetime.now()
                if "播报" in action:
                    reason += "/推送成功"
                else:
                    action += "/推送成功"
            elif is_test_mode:
                if "播报" in action:
                    reason += "/测试模式"
                else:
                    action += "/测试模式"
            else:
                if "播报" in action:
                    reason += "/无API服务"
        
        # Log Result
        print(f"[Debug] Process Result: {action} - {reason}")
        self._mark_led_dismissing(class_id, class_type)
        self._log_event(
            card_id,
            class_name,
            action,
            reason,
            class_type=class_type,
            source="刷卡",
            source_detail=card_id,
        )

    def process_manual_dismissal(self, params):
        class_id = str(params.get("classId") or "").strip()
        class_type = params.get("classType")
        teacher_id = params.get("triggerTeacherId")
        teacher_name = params.get("triggerTeacherName") or params.get("trigger_teacher_name")

        if not class_id:
            return {"result": "fail", "message": "classId is required"}

        command_key = "|".join(
            [
                str(params.get("commandId") or ""),
                str(class_type or ""),
                class_id,
                str(teacher_id or ""),
                str(teacher_name or ""),
            ]
        )
        if command_key in self.manual_command_history:
            return {"result": "success"}
        self.manual_command_history.add(command_key)

        class_info = self.db.get_class_info_by_class(class_id, class_type)
        effective_class_type = class_type if class_type is not None else class_info[3]
        class_name = (
            params.get("classVoiceName")
            or params.get("classShowName")
            or class_info[5]
            or class_info[4]
            or class_info[0]
        )

        if not class_name:
            self._log_event(
                "",
                "未知班级",
                "跳过",
                "服务端指令缺少班级信息",
                class_type=effective_class_type,
                source="服务端指令",
                source_detail=f"classId={class_id}",
            )
            return {"result": "fail", "message": f"class not found: {class_id}"}

        message = build_dismissal_voice_text(class_name)
        self.tts_worker.add_text(message)
        reason = "服务端指令"
        if teacher_name:
            reason += f"/{teacher_name}"
        self._log_event(
            "",
            class_name,
            "语音播报",
            reason,
            class_type=effective_class_type,
            source="服务端指令",
            source_detail=f"classId={class_id}",
        )
        self._mark_led_dismissing(class_id, effective_class_type)

        if self.api_service:
            import threading

            def push_api():
                self.api_service.push_dismissal_notice(
                    class_id,
                    None,
                    dismissal_status=params.get("dismissalStatus", 1),
                    class_type=effective_class_type,
                    trigger_type=2,
                    trigger_teacher_id=teacher_id,
                    trigger_teacher_name=teacher_name,
                )

            threading.Thread(target=push_api, daemon=True).start()

        return {"result": "success"}

    def _mark_led_dismissing(self, class_id, class_type=None):
        led_service = getattr(self, "led_service", None)
        try:
            is_administrative_class = int(class_type) == 1
        except (TypeError, ValueError):
            is_administrative_class = False
        if not led_service or not class_id or not is_administrative_class:
            return
        try:
            led_service.mark_dismissing(str(class_id))
        except Exception as exc:
            # LED is an auxiliary output. Never block voice or server reporting.
            print(f"[LED] Failed to queue class update: {exc}")

    def is_within_time_window(self, class_type=None):
        return self.get_current_window_signature(class_type=class_type) is not None

    def sync_led_window_state(self):
        active = self.is_within_time_window(class_type=1) or bool(
            self.config.get("test_mode", False)
        )
        led_service = getattr(self, "led_service", None)
        if led_service:
            led_service.set_dismissal_active(active)
        return active

    def _log_event(
        self,
        card_id,
        class_name,
        action,
        reason,
        class_type=None,
        source="刷卡",
        source_detail=None,
    ):
        # DB: Combine for backward compatibility
        full_status = f"{action} ({reason})" if reason else action
        self.db.log_swipe(
            card_id,
            class_name,
            full_status,
            source=source,
            source_detail=source_detail or card_id or "",
            class_type=class_type,
        )
        
        now = datetime.datetime.now()
        timestamp = now.strftime(DISPLAY_TIMESTAMP_FORMAT)
        now_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        # Emit Signal for UI
        from .class_types import format_class_type_label

        source_text = source
        if source == "刷卡" and (source_detail or card_id):
            source_text = f"刷卡 {source_detail or card_id}"
        self.log_updated.emit(
            timestamp,
            source_text,
            format_class_type_label(class_type),
            class_name,
            action,
            reason,
        )
        
        # File Logging
        try:
            log_file = os.path.join(self.log_dir, f"{date_str}.txt")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{now_str}] [Source:{source_text}] [Type:{format_class_type_label(class_type)}] "
                    f"[Name:{class_name}] [{action}] [{reason}]\n"
                )
        except Exception as e:
            print(f"[Log] File Write Error: {e}")

    def cleanup(self):
        self.tts_worker.stop()
        self.tts_thread.quit()
        self.tts_thread.wait()
