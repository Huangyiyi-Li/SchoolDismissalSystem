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
from src.services.broadcast_manager import TTSWorker, create_tts_engine


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
    init = create_tts_engine

    class PlaybackThread(QThread):
        def run(self):
            import pythoncom
            pythoncom.CoInitialize()
            stream = None
            try:
                def open_engine(stop_event):
                    nonlocal stream
                    from win32com.client import Dispatch
                    print(f"{name}: engine init", flush=True)
                    engine = init(stop_event)
                    print(f"{name}: engine ready", flush=True)
                    voice = engine.voice
                    evidence["voice"] = voice.Voice.GetDescription()
                    stream = Dispatch("SAPI.SpFileStream")
                    stream.Open(str(output.resolve()), 3)
                    voice.AudioOutputStream = stream
                    print(f"{name}: audio stream ready", flush=True)
                    say = engine.say
                    wait = engine.runAndWait

                    def record(entry):
                        evidence["events"].append(entry)
                        print(json.dumps({"case": name, **entry}), flush=True)

                    def say_and_record(text):
                        record({"event": "submitted", "text": text})
                        say(text)

                    def wait_and_record():
                        wait()
                        record({"event": "SAPI-completed"})

                    engine.say = say_and_record
                    engine.runAndWait = wait_and_record
                    return engine

                started = time.monotonic()
                with patch("src.services.broadcast_manager.create_tts_engine", open_engine):
                    # Hosted Windows has English voices; use a pronounceable
                    # fixture so empty Chinese synthesis cannot pass by accident.
                    TTSWorker(Config(count, interval))._play_text("Grade one, class one is leaving school")
                evidence["elapsed_seconds"] = time.monotonic() - started
            except Exception as exc:
                evidence["errors"].append(repr(exc))
            finally:
                if stream is not None:
                    stream.Close()
                pythoncom.CoUninitialize()

    thread = PlaybackThread()
    thread.start()
    deadline = time.monotonic() + 60
    while thread.isRunning() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        thread.wait(20)
    if thread.isRunning():
        print(json.dumps({"error": "TTS did not finish in 60 seconds", "case": name}), flush=True)
        (output_dir / f"{name}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
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


def native_probe(output_dir):
    """Check the Windows voice itself independently of pyttsx3 callbacks."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        for count in (1, 3):
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            output = output_dir / f"native-{count}.wav"
            stream.Open(str(output.resolve()), 3)
            voice.AudioOutputStream = stream
            try:
                print(f"native-{count}: speaking with {voice.Voice.GetDescription()}", flush=True)
                for _ in range(count):
                    voice.Speak("Grade one class one is leaving school", 0)
            finally:
                stream.Close()
            with wave.open(str(output)) as audio:
                print(json.dumps({"native_count": count,
                                  "audio_seconds": audio.getnframes() / audio.getframerate()}), flush=True)
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "tts-evidence")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"pyttsx3": version("pyttsx3"), "python": sys.version}), flush=True)
    native_probe(output_dir)
    baseline = probe(output_dir, 1, 0)
    natural = probe(output_dir, 3, 0)
    spaced = probe(output_dir, 3, 1)
    results = [baseline, natural, spaced]
    if any(result["errors"] for result in results):
        raise SystemExit(1)
    if baseline["audio_seconds"] < 0.5:
        raise SystemExit("Baseline contains no usable speech")
    for result in (natural, spaced):
        # Joining phrases removes the end-of-utterance silence between repeats.
        # For this fixed fixture, 3 natural repeats measure ~2.42x the single
        # utterance, while separately spoken repeats measure ~3x. Require more
        # than two utterances without incorrectly counting trimmed pauses.
        if result["audio_seconds"] < baseline["audio_seconds"] * 2.2:
            raise SystemExit("Real SAPI audio is shorter than three repeats")
    if spaced["elapsed_seconds"] < 2:
        raise SystemExit("Two configured one-second gaps were not observed")
