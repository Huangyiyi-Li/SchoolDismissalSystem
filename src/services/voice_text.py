import re


_DIGITS = "零一二三四五六七八九"
_DECIMAL_CLASS_RE = re.compile(r"(?<!\d)\s*(\d{1,2})\s*[.．]\s*(\d{1,2})\s*班")


def _to_chinese_number(value):
    number = int(value)
    if number < 0 or number > 99:
        return str(number)
    if number < 10:
        return _DIGITS[number]
    tens, ones = divmod(number, 10)
    prefix = "" if tens == 1 else _DIGITS[tens]
    suffix = "" if ones == 0 else _DIGITS[ones]
    return f"{prefix}十{suffix}"


def normalize_class_name_for_speech(class_name):
    """Convert compact numeric class names like 4.7班 into speech-friendly Chinese."""
    if not class_name:
        return class_name

    def replace_decimal_class(match):
        grade, class_no = match.groups()
        return f"{_to_chinese_number(grade)}年级{_to_chinese_number(class_no)}班"

    return _DECIMAL_CLASS_RE.sub(replace_decimal_class, str(class_name))


def build_dismissal_voice_text(class_name):
    return f"{normalize_class_name_for_speech(class_name)}正在放学"
