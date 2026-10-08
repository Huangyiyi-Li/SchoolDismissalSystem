import sys
import types
import unittest
from unittest.mock import patch


qtcore = types.ModuleType("PyQt6.QtCore")
qtcore.QObject = object
qtcore.pyqtSignal = lambda *args, **kwargs: None
qtcore.pyqtSlot = lambda *args, **kwargs: (lambda func: func)
qtcore.QThread = object
pyqt6 = types.ModuleType("PyQt6")
sys.modules.setdefault("PyQt6", pyqt6)
sys.modules.setdefault("PyQt6.QtCore", qtcore)
sys.modules.setdefault("pyttsx3", types.ModuleType("pyttsx3"))

from src.services.broadcast_manager import TTSWorker, play_tts_message
from src.services.tts_settings import TtsPlaybackSettings, normalize_tts_settings


class FakeEngine:
    def __init__(self):
        self.properties = []
        self.texts = []
        self.run_count = 0

    def setProperty(self, name, value):
        self.properties.append((name, value))

    def say(self, text):
        self.texts.append(text)

    def runAndWait(self):
        self.run_count += 1

    def stop(self):
        pass


class FakeConfig:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class TtsPlaybackTests(unittest.TestCase):
    def test_windows_worker_uses_offline_engine_without_sapi(self):
        engine = FakeEngine()
        worker = TTSWorker(FakeConfig({"tts_repeat_count": 3,
                                      "tts_repeat_interval_seconds": 0.01}))
        with patch("sys.platform", "win32"), \
                patch("src.services.offline_tts.OfflineMandarinEngine", return_value=engine) as offline, \
                patch("src.services.broadcast_manager.pyttsx3.init", create=True,
                      side_effect=AssertionError("Windows should not use system speech")):
            worker._play_text("一年级一班正在放学")
        offline.assert_called_once()
        self.assertEqual(engine.texts, ["一年级一班正在放学"] * 3)
        self.assertEqual(engine.run_count, 3)

    def test_native_wait_cancels_active_speech_when_worker_stops(self):
        import threading
        from src.services.windows_tts import WindowsSapiEngine
        stop_event = threading.Event()

        class Voice:
            def __init__(self):
                self.calls = []

            def Speak(self, text, flags):
                self.calls.append((text, flags))

            def WaitUntilDone(self, timeout):
                stop_event.set()
                return False

        voice = Voice()
        client = types.ModuleType("win32com.client")
        client.Dispatch = lambda name: voice
        win32com = types.ModuleType("win32com")
        win32com.client = client
        with patch.dict(sys.modules, {"win32com": win32com, "win32com.client": client}):
            engine = WindowsSapiEngine(stop_event)
            engine.say("一年级一班正在放学")
            engine.runAndWait()
        self.assertEqual(voice.calls, [("一年级一班正在放学", 17), ("", 3)])

    def test_invalid_and_out_of_range_settings_are_normalized(self):
        self.assertEqual(
            normalize_tts_settings("bad", "bad", "bad"),
            TtsPlaybackSettings(rate=0, repeat_count=3, interval_seconds=0),
        )
        self.assertEqual(
            normalize_tts_settings(1, 999, 999),
            TtsPlaybackSettings(rate=80, repeat_count=10, interval_seconds=10),
        )

    def test_interval_wait_can_stop_remaining_repeats(self):
        engine = FakeEngine()
        waits = []

        play_tts_message(
            engine,
            "一年级一班正在放学",
            rate=160,
            repeat_count=10,
            interval_seconds=10,
            wait_fn=lambda seconds: waits.append(seconds) or True,
        )

        self.assertEqual(engine.texts, ["一年级一班正在放学"])
        self.assertEqual(engine.run_count, 1)
        self.assertEqual(waits, [10])

    def test_natural_pause_submits_all_repeats_as_one_utterance(self):
        engine = FakeEngine()
        checks = []

        play_tts_message(
            engine,
            "一年级一班正在放学",
            repeat_count=3,
            interval_seconds=0,
            wait_fn=lambda seconds: checks.append(seconds) or False,
        )

        self.assertEqual(
            engine.texts,
            ["一年级一班正在放学，一年级一班正在放学，一年级一班正在放学"],
        )
        self.assertEqual(engine.run_count, 1)
        self.assertEqual(checks, [0, 0])

    def test_worker_reads_latest_settings_when_each_message_starts(self):
        config = FakeConfig({
            "tts_rate": 160,
            "tts_repeat_count": 2,
            "tts_repeat_interval_seconds": 0.6,
        })
        engine = FakeEngine()
        worker = TTSWorker(config)

        with patch(
            "src.services.broadcast_manager.create_tts_engine",
            return_value=engine,
            create=True,
        ), patch("src.services.broadcast_manager.play_tts_message") as play:
            worker._play_text("一年级一班正在放学")

        play.assert_called_once_with(
            engine,
            "一年级一班正在放学",
            rate=160,
            repeat_count=2,
            interval_seconds=0.6,
            wait_fn=worker._stop_event.wait,
        )

    def test_worker_stop_interrupts_interval_wait(self):
        worker = TTSWorker(FakeConfig({}))

        worker.stop()

        self.assertTrue(worker._stop_event.is_set())

    def test_system_default_preserves_natural_three_repeat_utterance(self):
        engine = FakeEngine()
        sleeps = []

        play_tts_message(
            engine,
            "一年级一班正在放学",
            rate=0,
            repeat_count=3,
            interval_seconds=0,
            sleep_fn=sleeps.append,
        )

        self.assertNotIn("rate", [name for name, _value in engine.properties])
        self.assertEqual(
            engine.texts,
            ["一年级一班正在放学，一年级一班正在放学，一年级一班正在放学"],
        )
        self.assertEqual(engine.run_count, 1)
        self.assertEqual(sleeps, [])

    def test_custom_rate_repeat_and_interval_are_applied_between_repeats(self):
        engine = FakeEngine()
        sleeps = []

        play_tts_message(
            engine,
            "一年级一班正在放学",
            rate=160,
            repeat_count=2,
            interval_seconds=0.6,
            sleep_fn=sleeps.append,
        )

        self.assertIn(("rate", 160), engine.properties)
        self.assertEqual(
            engine.texts,
            ["一年级一班正在放学", "一年级一班正在放学"],
        )
        self.assertEqual(engine.run_count, 2)
        self.assertEqual(sleeps, [0.6])


if __name__ == "__main__":
    unittest.main()
