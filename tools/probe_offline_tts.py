"""Generate real Mandarin WAVs on Windows before packaging the client."""

import sys
import wave
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.offline_tts import OfflineMandarinEngine


def synthesize(text, target):
    def capture(source, duration, stop_event):
        target.write_bytes(source.read_bytes())

    engine = OfflineMandarinEngine(Event(), player=capture)
    try:
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()
    with wave.open(str(target)) as audio:
        return audio.getnframes() / audio.getframerate()


if __name__ == "__main__":
    output = Path("tts-evidence")
    output.mkdir(exist_ok=True)
    phrase = "一年级一班正在放学，请家长到校门口接孩子。"
    one = synthesize(phrase, output / "mandarin-once.wav")
    three = synthesize("，".join([phrase] * 3), output / "mandarin-three.wav")
    print(f"Offline Mandarin WAV duration: once={one:.2f}s, three={three:.2f}s", flush=True)
    if one < 0.5 or three < one * 2:
        raise SystemExit("Offline Mandarin speech was empty or repeated text was truncated")
