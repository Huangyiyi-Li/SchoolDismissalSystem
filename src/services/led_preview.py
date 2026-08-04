from PIL import Image, ImageOps


PREVIEW_BACKGROUND = (5, 0, 0)
PREVIEW_LED_RED = (255, 48, 32)


def colorize_led_preview(source_path):
    with Image.open(source_path) as source:
        grayscale = source.convert("L")
        return ImageOps.colorize(
            grayscale,
            black=PREVIEW_BACKGROUND,
            white=PREVIEW_LED_RED,
        )


def scaled_preview_size(width, height, zoom_percent):
    scale = max(1, int(zoom_percent)) / 100
    return (
        max(1, round(int(width) * scale)),
        max(1, round(int(height) * scale)),
    )
