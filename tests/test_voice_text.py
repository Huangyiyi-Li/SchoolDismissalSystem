import unittest

from src.services.voice_text import build_dismissal_voice_text, normalize_class_name_for_speech


class VoiceTextTests(unittest.TestCase):
    def test_decimal_style_class_name_reads_as_grade_and_class(self):
        self.assertEqual(normalize_class_name_for_speech("4.7班"), "四年级七班")
        self.assertEqual(normalize_class_name_for_speech("5.15 班"), "五年级十五班")

    def test_build_dismissal_voice_text_uses_speech_friendly_class_name(self):
        self.assertEqual(build_dismissal_voice_text("4.7班"), "四年级七班正在放学")

    def test_non_decimal_class_name_is_preserved(self):
        self.assertEqual(normalize_class_name_for_speech("一年级一班"), "一年级一班")


if __name__ == "__main__":
    unittest.main()
