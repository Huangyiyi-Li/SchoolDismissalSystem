"""Exercise the real Windows TTS worker and retain audio/evidence, without a school."""
import json
import sys
import time
import wave
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QCoreApplication, QThread
import pyttsx3
from src.services.broadcast_manager import TTSWorker


class Config:
    def __init__(self, count, interval):
        self.values = {"tts_repeat_count": count,
                       "tts_repeat_interval_seconds": interval, "tts_rate": 0}

    def get(self, key, default=None):
        return self.values.get(key, default)


def probe(output_dir, count, interval):
    name = f"repeat-{count}-interval-{interval}"
    output = output_dir / f"{name}.wav"
    evidence = {"count": count, "interval": interval, "events": [], "errors": []}
    init = pyttsx3.init

    class PlaybackThread(QThread):
        def run(self):
            import pythoncom
            pythoncom.CoInitialize()
            stream = None
            try:
                def open_engine():
                    nonlocal stream
                    import comtypes.client
                    engine = init("sapi5")
                    voice = engine.proxy._driver._tts
                    evidence["voice"] = voice.Voice.GetDescription()
                    stream = comtypes.client.CreateObject("SAPI.SpFileStream")
                    stream.Open(str(output.resolve()), 3)
                    voice.AudioOutputStream = stream
                    for event in ("started-utterance", "started-word", "finished-utterance", "error"):
                        engine.connect(event, lambda event=event, **kwargs:
                                       evidence["events"].append({"event": event, **kwargs}))
                    return engine

                started = time.monotonic()
                with patch("src.services.broadcast_manager.pyttsx3.init", open_engine):
                    TTSWorker(Config(count, interval))._play_text("一年级一班正在放学")
                evidence["elapsed_seconds"] = time.monotonic() - started
            except Exception as exc:
                evidence["errors"].append(repr(exc))
            finally:
                if stream is not None:
                    stream.Close()
                pythoncom.CoUninitialize()

    thread = PlaybackThread()
    thread.start()
    if not thread.wait(60000):
        print(json.dumps({"error": "TTS did not finish in 60 seconds", "case": name}), flush=True)
        import os
        os._exit(2)
    try:
        with wave.open(str(output)) as audio:
            evidence["audio_seconds"] = audio.getnframes() / audio.getframerate()
    except Exception as exc:
        evidence["errors"].append(repr(exc))
    print(json.dumps({"case": name, **evidence}, ensure_ascii=False), flush=True)
    (output_dir / f"{name}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "tts-evidence")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"pyttsx3": version("pyttsx3"), "python": sys.version}), flush=True)
    baseline = probe(output_dir, 1, 0)
    natural = probe(output_dir, 3, 0)
    spaced = probe(output_dir, 3, 1)
    results = [baseline, natural, spaced]
    if any(result["errors"] for result in results):
        raise SystemExit(1)
    for result in (natural, spaced):
        if result["audio_seconds"] < baseline["audio_seconds"] * 2.5:
            raise SystemExit("Real SAPI audio is shorter than three repeats")
