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
    regions: list

    @property
    def rows(self):
        """Backward-compatible flattened access for one-region callers/tests."""
        return [row for region in self.regions for row in region]


@dataclass(frozen=True)
class LedPageLayout:
    pages: list
    max_columns: int


def _ordered_unique_classes(classes):
    seen = set()
    ordered = []
    for item in sorted(classes, key=lambda value: int(value.get("source_order", 0))):
        class_id = str(item.get("class_id") or "").strip()
        key = (int(item.get("class_type") or 1), class_id)
        if not class_id or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _build_rows(classes, class_type):
    ordered = _ordered_unique_classes(classes)
    if int(class_type or 1) == 2:
        return [
            GradeRow(
                str(
                    item.get("class_show_name")
                    or item.get("class_name")
                    or "社团班"
                ).strip(),
                [item],
            )
            for item in ordered
        ]

    grade_order = []
    grouped = {}
    for item in ordered:
        grade_name = str(item.get("grade_name") or "").strip()
        if not grade_name:
            continue
        if grade_name not in grouped:
            grouped[grade_name] = []
            grade_order.append(grade_name)
        grouped[grade_name].append(item)
    return [GradeRow(name, grouped[name]) for name in grade_order]


def build_led_page_layout(
    classes,
    grades_per_page=2,
    regions_per_page=1,
    class_type=1,
):
    rows_per_region = max(1, int(grades_per_page))
    region_count = max(1, int(regions_per_page))
    rows = _build_rows(classes, class_type)
    max_columns = max((len(row.classes) for row in rows), default=0)
    rows_per_screen = rows_per_region * region_count
    pages = []
    for page_start in range(0, len(rows), rows_per_screen):
        screen_rows = rows[page_start:page_start + rows_per_screen]
        regions = [
            screen_rows[index:index + rows_per_region]
            for index in range(0, rows_per_screen, rows_per_region)
        ]
        while len(regions) < region_count:
            regions.append([])
        pages.append(LedPage(regions=regions))
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


def _fit_font(draw, text, max_width, max_height, preferred=20, minimum=8):
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
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = x1 + ((x2 - x1) - text_width) / 2 - bounds[0]
    y = y1 + ((y2 - y1) - text_height) / 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=1)


def _draw_title(draw, title, box):
    lines = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if not lines:
        return
    x1, y1, x2, y2 = box
    line_height = (y2 - y1) / len(lines)
    for index, line in enumerate(lines):
        _draw_centered(
            draw,
            (x1, int(y1 + index * line_height), x2, int(y1 + (index + 1) * line_height)),
            line,
            preferred=22,
        )


def _status_for(statuses, item):
    class_id = str(item.get("class_id") or "")
    class_type = int(item.get("class_type") or 1)
    return statuses.get((class_type, class_id), statuses.get(class_id, ""))


def render_led_pages(
    school_title,
    classes,
    statuses,
    output_dir,
    width=1024,
    height=96,
    grades_per_page=2,
    regions_per_page=1,
    show_title=True,
    class_type=1,
    filename_prefix="led-page",
):
    rows_per_region = max(1, int(grades_per_page))
    region_count = max(1, int(regions_per_page))
    layout = build_led_page_layout(
        classes,
        grades_per_page=rows_per_region,
        regions_per_page=region_count,
        class_type=class_type,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob(f"{filename_prefix}-*.bmp"):
        stale.unlink()

    if not layout.pages:
        return []

    # Shrink labels on small contractor-provided screen sizes instead of
    # allowing their fixed minimums to consume the entire content area.
    title_width = min(170, max(1, width // 7)) if show_title else 0
    content_width = width - title_width
    region_width = content_width / region_count
    header_height = max(1, height // (rows_per_region + 1))
    paths = []

    for page_index, page in enumerate(layout.pages, start=1):
        image = Image.new("1", (width, height), 0)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=1)

        if show_title:
            draw.line((title_width, 0, title_width, height), fill=1)
            _draw_title(draw, school_title, (0, 0, title_width, height))

        for region_index in range(region_count):
            rows = page.regions[region_index] if region_index < len(page.regions) else []
            region_x1 = round(title_width + region_width * region_index)
            region_x2 = round(title_width + region_width * (region_index + 1))
            if region_index:
                draw.line((region_x1, 0, region_x1, height), fill=1)
            grade_width = min(
                90,
                max(1, int((region_x2 - region_x1) * 0.18)),
            )
            data_x1 = region_x1 + grade_width
            draw.line((data_x1, 0, data_x1, height), fill=1)
            draw.line((region_x1, header_height, region_x2, header_height), fill=1)

            region_columns = max((len(row.classes) for row in rows), default=1)
            class_width = max(1, (region_x2 - data_x1) / region_columns)
            for column in range(1, region_columns):
                x = round(data_x1 + class_width * column)
                draw.line((x, 0, x, height), fill=1)
            for row_index in range(1, rows_per_region):
                y = header_height * (row_index + 1)
                draw.line((region_x1, y, region_x2, y), fill=1)

            for column in range(region_columns):
                x1 = round(data_x1 + class_width * column)
                x2 = round(data_x1 + class_width * (column + 1))
                header = "状态" if int(class_type or 1) == 2 else f"{column + 1}班"
                _draw_centered(draw, (x1, 0, x2, header_height), header, preferred=18)

            for row_index, row in enumerate(rows):
                y1 = header_height * (row_index + 1)
                y2 = (
                    header_height * (row_index + 2)
                    if row_index < rows_per_region - 1
                    else height
                )
                _draw_centered(
                    draw,
                    (region_x1, y1, data_x1, y2),
                    row.grade_name,
                    preferred=18,
                )
                for column, item in enumerate(row.classes):
                    x1 = round(data_x1 + class_width * column)
                    x2 = round(data_x1 + class_width * (column + 1))
                    _draw_centered(
                        draw,
                        (x1, y1, x2, y2),
                        _status_for(statuses, item),
                        preferred=18,
                    )

        path = output_dir / f"{filename_prefix}-{page_index:02d}.bmp"
        image.save(path, format="BMP")
        paths.append(path)

    return paths
