from dataclasses import dataclass
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class GradeRow:
    grade_name: str
    classes: list


@dataclass(frozen=True)
class LedPage:
    rows: list


@dataclass(frozen=True)
class LedPageLayout:
    pages: list
    max_columns: int


def build_led_page_layout(classes, grades_per_page=2):
    grade_order = []
    grouped = {}
    for item in sorted(classes, key=lambda value: int(value.get("source_order", 0))):
        grade_name = str(item.get("grade_name") or "").strip()
        if not grade_name:
            continue
        if grade_name not in grouped:
            grouped[grade_name] = []
            grade_order.append(grade_name)
        # The database is unique by classId, but keep this function safe for
        # callers that pass raw service data.
        class_id = str(item.get("class_id") or "")
        if class_id and any(str(existing.get("class_id") or "") == class_id for existing in grouped[grade_name]):
            continue
        grouped[grade_name].append(item)

    rows = [GradeRow(name, grouped[name]) for name in grade_order]
    max_columns = max((len(row.classes) for row in rows), default=0)
    pages = [
        LedPage(rows[index:index + grades_per_page])
        for index in range(0, len(rows), grades_per_page)
    ]
    return LedPageLayout(pages=pages, max_columns=max_columns)


def _font_candidates():
    windows = os.environ.get("WINDIR", r"C:\Windows")
    return [
        Path(windows) / "Fonts" / "simhei.ttf",
        Path(windows) / "Fonts" / "msyh.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _load_font(size):
    for candidate in _font_candidates():
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fit_font(draw, text, max_width, max_height, preferred=20, minimum=10):
    for size in range(preferred, minimum - 1, -1):
        font = _load_font(size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width and box[3] - box[1] <= max_height:
            return font
    return _load_font(minimum)


def _draw_centered(draw, box, text, preferred=20):
    if not text:
        return
    x1, y1, x2, y2 = box
    font = _fit_font(draw, text, max(1, x2 - x1 - 4), max(1, y2 - y1 - 2), preferred)
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = x1 + ((x2 - x1) - width) / 2 - bounds[0]
    y = y1 + ((y2 - y1) - height) / 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=1)


def _draw_title(draw, title, box):
    lines = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if not lines:
        lines = ["放学系统"]
    x1, y1, x2, y2 = box
    line_height = (y2 - y1) / len(lines)
    for index, line in enumerate(lines):
        _draw_centered(
            draw,
            (x1, int(y1 + index * line_height), x2, int(y1 + (index + 1) * line_height)),
            line,
            preferred=22,
        )


def render_led_pages(
    school_title,
    classes,
    statuses,
    output_dir,
    width=1024,
    height=96,
    grades_per_page=2,
):
    layout = build_led_page_layout(classes, grades_per_page=grades_per_page)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob("led-page-*.bmp"):
        stale.unlink()

    if not layout.pages:
        return []

    title_width = min(170, max(120, width // 7))
    grade_width = min(90, max(64, width // 12))
    header_height = height // (grades_per_page + 1)
    class_width = (width - title_width - grade_width) / max(1, layout.max_columns)
    paths = []

    for page_index, page in enumerate(layout.pages, start=1):
        image = Image.new("1", (width, height), 0)
        draw = ImageDraw.Draw(image)

        draw.rectangle((0, 0, width - 1, height - 1), outline=1)
        draw.line((title_width, 0, title_width, height), fill=1)
        draw.line((title_width + grade_width, 0, title_width + grade_width, height), fill=1)
        draw.line((title_width, header_height, width, header_height), fill=1)
        for row_index in range(1, grades_per_page):
            y = header_height * (row_index + 1)
            draw.line((title_width, y, width, y), fill=1)
        for column in range(1, layout.max_columns):
            x = round(title_width + grade_width + class_width * column)
            draw.line((x, 0, x, height), fill=1)

        _draw_title(draw, school_title, (0, 0, title_width, height))
        for column in range(layout.max_columns):
            x1 = round(title_width + grade_width + class_width * column)
            x2 = round(title_width + grade_width + class_width * (column + 1))
            _draw_centered(draw, (x1, 0, x2, header_height), f"{column + 1}班", preferred=18)

        for row_index, row in enumerate(page.rows):
            y1 = header_height * (row_index + 1)
            y2 = header_height * (row_index + 2) if row_index < grades_per_page - 1 else height
            _draw_centered(draw, (title_width, y1, title_width + grade_width, y2), row.grade_name, preferred=18)
            for column, item in enumerate(row.classes):
                x1 = round(title_width + grade_width + class_width * column)
                x2 = round(title_width + grade_width + class_width * (column + 1))
                status = statuses.get(str(item.get("class_id") or ""), "")
                _draw_centered(draw, (x1, y1, x2, y2), status, preferred=18)

        path = output_dir / f"led-page-{page_index:02d}.bmp"
        image.save(path, format="BMP")
        paths.append(path)

    return paths
