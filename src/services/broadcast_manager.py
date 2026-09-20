from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import pyttsx3
import datetime
import time
import queue
import threading

from .voice_text import build_dismissal_voice_text
from .broadcast_mode import get_effective_window_signature
from .dismissal_window import get_active_window_signature, is_led_output_active
from .log_records import DISPLAY_TIMESTAMP_FORMAT
from .tts_settings import normalize_tts_settings, tts_settings_from_config


def play_tts_message(
    engine,
    text,
    rate=0,
    repeat_count=3,
    interval_seconds=0,
    sleep_fn=time.sleep,
    wait_fn=None,
):
    """Play one message using the configured voice rhythm."""
    settings = normalize_tts_settings(rate, repeat_count, interval_seconds)
    if settings.rate:
        engine.setProperty("rate", settings.rate)

    if settings.interval_seconds == 0:
        if wait_fn is None:
            engine.say("，".join([text] * settings.repeat_count))
            engine.runAndWait()
            return
        for index in range(settings.repeat_count):
            if wait_fn(0):
                return
            suffix = "，" if index < settings.repeat_count - 1 else ""
            engine.say(f"{text}{suffix}")
            engine.runAndWait()
            if wait_fn(0):
                return
        return

    for index in range(settings.repeat_count):
        engine.say(text)
        engine.runAndWait()
        if index < settings.repeat_count - 1:
            if wait_fn is not None:
                if wait_fn(settings.interval_seconds):
                    return
            else:
                sleep_fn(settings.interval_seconds)


class TTSWorker(QObject):
    finished = pyqtSignal()
    
    def __init__(self, config_manager=None):
        super().__init__()
        self.config = config_manager
        self.queue = queue.Queue()
        self.retry_count = 3
        self.running = True
        self._stop_event = threading.Event()

    def add_text(self, text):
        self.queue.put(text)

    def _play_text(self, text):
        if self._stop_event.is_set():
            return
        engine = pyttsx3.init()
        try:
            engine.setProperty("volume", 1.0)
            settings = (
                tts_settings_from_config(self.config)
                if self.config is not None
                else normalize_tts_settings(0, 3, 0)
            )
            play_tts_message(
                engine,
                text,
                rate=settings.rate,
                repeat_count=settings.repeat_count,
                interval_seconds=settings.interval_seconds,
                wait_fn=self._stop_event.wait,
            )
        finally:
            engine.stop()

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
                        self._play_text(text)
                    except Exception as e_inner:
                         print(f"[TTS] Inner Loop Error: {e_inner}")

                    self._stop_event.wait(0.5)
                else:
                    self._stop_event.wait(0.1)
            except Exception as e:
                print(f"[TTS] Playback Error: {e}")
                self._stop_event.wait(1)
        
        # Cleanup COM in the WORKER THREAD
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except:
            pass

    def stop(self):
        self.running = False
        self._stop_event.set()
        # Do NOT uninitialize COM here, as this runs in Main Thread!


class BroadcastManager(QObject):
    log_updated = pyqtSignal(str, str, str, str, str, str) # time, source, type, name, action, reason
    queue_updated = pyqtSignal(list) # list of class names

    def __init__(
        self,
        config_manager,
        db_manager,
        api_service=None,
        led_service=None,
        operation_logger=None,
    ):
        super().__init__()
        self.config = config_manager
        self.db = db_manager
        self.api_service = api_service
        self.led_service = led_service
        self.operation_logger = operation_logger
        
        # Deduplication state
        self.voice_history = {}
        self.api_push_history = {}
        self.manual_command_history = set()
        
        # TTS Thread
        self.tts_thread = QThread()
        self.tts_worker = TTSWorker(self.config)
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

    def process_credential(self, event):
        if event.credential_type == 'legacy_card':
            self.process_swipe(event.credential_id, event.reader_ip)
            return
        if event.credential_type != 'uhf_epc':
            return
        card_id = self.db.resolve_credential(self.config.get('school_id'), event.credential_id)
        detail = f"{event.credential_id} / {event.reader_id} / {event.reader_ip}"
        if not card_id:
            self._log_event(event.credential_id, "未知", "跳过", "标签未绑定或绑定已失效",
                            source="超高频标签", source_detail=detail)
            return
        self._process_card(card_id, event.reader_ip, "超高频标签", detail)

    def process_swipe(self, card_id, ip):
        self._process_card(card_id, ip)

    def _process_card(self, card_id, ip, source="刷卡", source_detail=None):
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
                source=source,
                source_detail=source_detail or card_id,
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
                source=source,
                source_detail=source_detail or card_id,
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
            source=source,
            source_detail=source_detail or card_id,
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

        # A valid server command is itself an explicit display trigger.  Keep
        # the existing schedule state untouched so an administrative command
        # cannot clear a concurrently active club/grade type.
        led_service = getattr(self, "led_service", None)
        if led_service and hasattr(led_service, "set_dismissal_active"):
            try:
                led_service.set_dismissal_active(True)
            except (TypeError, RuntimeError):
                pass

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

    def simulate_class_swipe(self, class_id, class_type=1):
        """Simulate an administrative-class swipe without contacting the server."""
        if not self.config.get("test_mode", False):
            return {"result": "fail", "message": "请先开启测试模式"}

        class_id = str(class_id or "").strip()
        class_type = int(class_type or 1)
        school_id = self.config.get("school_id")
        classes = self.db.get_led_classes(school_id, class_type=class_type)
        class_info = next(
            (
                item
                for item in classes
                if str(item.get("class_id") or "").strip() == class_id
            ),
            None,
        )
        if class_info is None:
            class_type_label = "社团班" if class_type == 2 else "行政班"
            return {
                "result": "fail",
                "message": f"未找到该{class_type_label}，请先同步学校数据",
            }

        class_name = (
            class_info.get("class_voice_name")
            or class_info.get("class_show_name")
            or class_info.get("class_name")
        )
        if not class_name:
            return {
                "result": "fail",
                "message": "该班级缺少可播报名称，请先同步学校数据",
            }

        # Test mode also owns the LED outside the configured dismissal window.
        self.sync_led_window_state()
        self.tts_worker.add_text(build_dismissal_voice_text(class_name))
        self._mark_led_dismissing(class_id, class_type)
        self._log_event(
            "",
            class_name,
            "语音播报",
            "测试模式/本地模拟，不推送服务端",
            class_type=class_type,
            source="模拟刷卡",
            source_detail=f"classId={class_id}",
        )
        return {"result": "success", "message": f"已模拟{class_name}刷卡"}

    def _mark_led_dismissing(self, class_id, class_type=None):
        led_service = getattr(self, "led_service", None)
        try:
            normalized_class_type = int(class_type)
        except (TypeError, ValueError):
            normalized_class_type = 0
        if not led_service or not class_id or normalized_class_type not in (1, 2):
            return
        try:
            led_service.mark_dismissing(
                str(class_id),
                class_type=normalized_class_type,
            )
        except Exception as exc:
            # LED is an auxiliary output. Never block voice or server reporting.
            print(f"[LED] Failed to queue class update: {exc}")

    def is_within_time_window(self, class_type=None):
        return self.get_current_window_signature(class_type=class_type) is not None

    def sync_led_window_state(self):
        test_mode = bool(self.config.get("test_mode", False))
        active_types = {
            class_type
            for class_type in (1, 2)
            if self.is_within_time_window(class_type=class_type)
        }
        if test_mode:
            active_types = {1, 2}
        active = is_led_output_active(bool(active_types), self.config)
        led_service = getattr(self, "led_service", None)
        if led_service:
            if hasattr(led_service, "set_test_mode"):
                led_service.set_test_mode(test_mode)
            try:
                led_service.set_dismissal_active(active, class_types=active_types)
            except TypeError:
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
        
        # Emit Signal for UI
        from .class_types import format_class_type_label

        source_text = source
        if source == "刷卡" and (source_detail or card_id):
            source_text = f"刷卡 {source_detail or card_id}"
        elif source == "超高频标签" and card_id:
            source_text = f"超高频标签 {card_id}"
        self.log_updated.emit(
            timestamp,
            source_text,
            format_class_type_label(class_type),
            class_name,
            action,
            reason,
        )

        operation_logger = getattr(self, "operation_logger", None)
        if operation_logger:
            try:
                operation_logger.record(
                    category="放学业务",
                    action=action,
                    target=class_name,
                    result="fail" if "跳过" in action else "success",
                    detail=reason,
                    source=source_text,
                )
            except Exception as exc:
                print(f"[Log] Operation Log Write Error: {exc}")
        
    def cleanup(self):
        self.tts_worker.stop()
        self.tts_thread.quit()
        self.tts_thread.wait()
