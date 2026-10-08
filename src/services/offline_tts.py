"""Portable Mandarin speech synthesis and WAV playback, independent of SAPI."""

import sys
import time
import wave
from pathlib import Path
from tempfile import TemporaryDirectory


MODEL_DIRECTORY = "vits-melo-tts-zh_en"


def model_path():
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    return root / "offline-tts" / MODEL_DIRECTORY


class OfflineMandarinEngine:
    def __init__(self, stop_event, model_dir=None, player=None):
        import sherpa_onnx

        self.stop_event = stop_event
        self.model_dir = Path(model_dir) if model_dir is not None else model_path()
        for name in ("model.onnx", "lexicon.txt", "tokens.txt", "date.fst", "number.fst"):
            if not (self.model_dir / name).is_file():
                raise FileNotFoundError(f"离线语音模型缺少 {name}: {self.model_dir}")
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(self.model_dir / "model.onnx"),
                    lexicon=str(self.model_dir / "lexicon.txt"),
                    tokens=str(self.model_dir / "tokens.txt"),
                ),
                provider="cpu",
                num_threads=2,
            ),
            rule_fsts=",".join(str(self.model_dir / name) for name in ("date.fst", "number.fst")),
        )
        if not config.validate():
            raise RuntimeError("离线语音模型配置无效")
        self.tts = sherpa_onnx.OfflineTts(config)
        self.sherpa = sherpa_onnx
        self.player = player
        self.rate = 1.0
        self.volume = 1.0
        self.text = None
        self._temporary = TemporaryDirectory(prefix="school-dismissal-tts-")
        self._wav = Path(self._temporary.name) / "speech.wav"

    def setProperty(self, name, value):
        if name == "volume":
            self.volume = min(1.0, max(0.0, float(value)))
        elif name == "rate":
            self.rate = max(0.5, min(2.0, float(value) / 160))
        else:
            raise ValueError(f"Unsupported offline speech property: {name}")

    def say(self, text):
        self.text = text

    def runAndWait(self):
        if self.stop_event.is_set() or not self.text:
            return
        settings = self.sherpa.GenerationConfig()
        settings.speed = self.rate
        audio = self.tts.generate(self.text, settings)
        if len(audio.samples) == 0:
            raise RuntimeError("离线语音引擎没有生成音频")
        if self.stop_event.is_set():
            return
        # sherpa-onnx returns normalized float samples. WAV uses the ordinary
        # Windows audio output path and never creates a SAPI/OneCore object.
        pcm = (audio.samples.clip(-1, 1) * 32767 * self.volume).astype("<i2")
        with wave.open(str(self._wav), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(audio.sample_rate)
            output.writeframes(pcm.tobytes())
        duration = len(audio.samples) / audio.sample_rate
        if self.player is not None:
            self.player(self._wav, duration, self.stop_event)
        else:
            self._play_windows(duration)

    def _play_windows(self, duration):
        import winsound

        winsound.PlaySound(str(self._wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
        try:
            deadline = time.monotonic() + duration
            while not self.stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.stop_event.wait(min(remaining, 0.05))
        finally:
            winsound.PlaySound(None, 0)

    def stop(self):
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, 0)
        self._temporary.cleanup()
