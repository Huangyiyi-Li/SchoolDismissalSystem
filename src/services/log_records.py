import datetime


DISPLAY_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_log_timestamp(value):
    if isinstance(value, datetime.datetime):
        return value.strftime(DISPLAY_TIMESTAMP_FORMAT)

    text = str(value or "")
    try:
        parsed = datetime.datetime.strptime(text, DISPLAY_TIMESTAMP_FORMAT)
        return parsed.strftime(DISPLAY_TIMESTAMP_FORMAT)
    except ValueError:
        return text
