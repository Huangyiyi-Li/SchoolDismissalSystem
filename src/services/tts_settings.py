from dataclasses import dataclass


@dataclass(frozen=True)
class TtsPlaybackSettings:
    rate: int = 0
    repeat_count: int = 3
    interval_seconds: float = 0


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_tts_settings(rate, repeat_count, interval_seconds):
    parsed_rate = _as_int(rate, 0)
    if parsed_rate <= 0:
        parsed_rate = 0
    else:
        parsed_rate = min(300, max(80, parsed_rate))

    parsed_repeat_count = min(10, max(1, _as_int(repeat_count, 3)))
    parsed_interval = min(10.0, max(0.0, _as_float(interval_seconds, 0)))
    return TtsPlaybackSettings(
        rate=parsed_rate,
        repeat_count=parsed_repeat_count,
        interval_seconds=parsed_interval,
    )


def tts_settings_from_config(config):
    return normalize_tts_settings(
        config.get("tts_rate", 0),
        config.get("tts_repeat_count", 3),
        config.get("tts_repeat_interval_seconds", 0),
    )
