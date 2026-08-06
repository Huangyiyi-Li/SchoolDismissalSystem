from PIL import Image, ImageOps


class PreviewRefreshState:
    """Track explicit preview requests without coupling state to Qt widgets."""

    def __init__(self):
        self.revision = 0
        self.running = False
        self.has_preview = False
        self.dirty = False

    @property
    def button_label(self):
        if self.running:
            return "正在生成…"
        return "重新生成预览" if self.has_preview else "生成预览"

    def mark_dirty(self):
        self.revision += 1
        self.dirty = True
        return self.revision

    def begin(self):
        if self.running:
            return None
        self.running = True
        return self.revision

    def complete(self, request_revision, success):
        self.running = False
        stale = request_revision != self.revision
        if success:
            self.has_preview = True
        self.dirty = stale or not success
        return stale


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
