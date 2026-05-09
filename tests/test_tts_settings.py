import unittest

from src.services.tts_settings import (
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOLUME,
    MAX_TTS_RATE,
    MAX_TTS_VOLUME,
    MIN_TTS_RATE,
    MIN_TTS_VOLUME,
    normalize_tts_rate,
    normalize_tts_volume,
)


class TTSSettingsTests(unittest.TestCase):
    def test_normalize_tts_rate_clamps_to_supported_range(self):
        self.assertEqual(normalize_tts_rate(40), MIN_TTS_RATE)
        self.assertEqual(normalize_tts_rate(999), MAX_TTS_RATE)

    def test_normalize_tts_rate_falls_back_to_default(self):
        self.assertEqual(normalize_tts_rate("fast"), DEFAULT_TTS_RATE)

    def test_normalize_tts_volume_clamps_to_supported_range(self):
        self.assertEqual(normalize_tts_volume(0.01), MIN_TTS_VOLUME)
        self.assertEqual(normalize_tts_volume(2.5), MAX_TTS_VOLUME)

    def test_normalize_tts_volume_falls_back_to_default(self):
        self.assertEqual(normalize_tts_volume("loud"), DEFAULT_TTS_VOLUME)


if __name__ == "__main__":
    unittest.main()
