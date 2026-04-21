from __future__ import annotations

DEFAULT_TTS_RATE = 160
DEFAULT_TTS_VOLUME = 1.0
MIN_TTS_RATE = 80
MAX_TTS_RATE = 240
MIN_TTS_VOLUME = 0.2
MAX_TTS_VOLUME = 1.0


def normalize_tts_rate(value, default: int = DEFAULT_TTS_RATE) -> int:
    try:
        rate = int(value)
    except (TypeError, ValueError):
        rate = int(default)
    return max(MIN_TTS_RATE, min(MAX_TTS_RATE, rate))


def normalize_tts_volume(value, default: float = DEFAULT_TTS_VOLUME) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        volume = float(default)
    return max(MIN_TTS_VOLUME, min(MAX_TTS_VOLUME, volume))

