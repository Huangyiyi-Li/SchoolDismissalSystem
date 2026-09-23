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


def colorize_led_preview(source_path, color_mode="single"):
    with Image.open(source_path) as source:
        if str(color_mode or "").strip().lower() == "double":
            return source.convert("RGB")
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


def preview_readability_warning(metric, width, height):
    """Explain when the native LED bitmap is too dense to read after zooming."""
    sizes = [int(metric.get(key) or 0) for key in ('title_px', 'header_px', 'cell_px')]
    sizes = [size for size in sizes if size > 0]
    if not sizes or min(sizes) >= 8:
        return ''
    suggestions = []
    if metric.get('row_count', 0) > 2:
        suggestions.append('把年级拆到更多轮播页')
    if metric.get('column_count', 0) >= 4 and metric.get('max_status_chars', 0) > 1:
        suggestions.append('将状态文案改为单字或空心/实心圆')
    if metric.get('title_px', 0) and metric['title_px'] < 8:
        suggestions.append('缩短或隐藏标题')
    if not suggestions:
        suggestions.append('减少同页内容，或使用更宽的屏幕')
    return (f'当前 {width}×{height} 原生像素中最小文字仅 {min(sizes)} px，实体屏难以辨认；'
            '放大预览不会增加屏幕像素。建议' + '，'.join(suggestions) + '。')
