from dataclasses import dataclass
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont


LED_RED = (255, 0, 0)
LED_YELLOW = (255, 255, 0)
LED_GREEN = (0, 255, 0)
LED_BLACK = (0, 0, 0)


def normalize_color_mode(value):
    return "double" if str(value or "").strip().lower() == "double" else "single"


def display_status(status, color_mode="single"):
    status = str(status or "").strip()
    if normalize_color_mode(color_mode) == "double" and not status:
        return "未放学"
    return status


def status_color(status, color_mode="single"):
    if normalize_color_mode(color_mode) != "double":
        return 1
    status = str(status or "").strip()
    if status == "已放学":
        return LED_GREEN
    if status == "放学中":
        return LED_RED
    return LED_YELLOW


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


def _draw_centered(draw, box, text, preferred=20, fill=1):
    if not text:
        return
    x1, y1, x2, y2 = box
    font = _fit_font(draw, text, max(1, x2 - x1 - 4), max(1, y2 - y1 - 2), preferred)
    bounds = draw.textbbox((0, 0), text, font=font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = x1 + ((x2 - x1) - text_width) / 2 - bounds[0]
    y = y1 + ((y2 - y1) - text_height) / 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=fill)


def split_club_name(text):
    text = str(text or "").strip()
    if len(text) <= 1:
        return [text] if text else []
    split_at = (len(text) + 1) // 2
    return [text[:split_at], text[split_at:]]


def calculate_club_column_widths(group_width):
    group_width = max(2, int(group_width))
    status_width = max(28, round(group_width * 0.42))
    status_width = min(group_width - 1, status_width)
    return group_width - status_width, status_width


def _line_metrics(draw, lines, font):
    widths = []
    heights = []
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=font)
        widths.append(bounds[2] - bounds[0])
        heights.append(bounds[3] - bounds[1])
    return widths, heights


def _draw_centered_lines(draw, box, lines, font, fill=1):
    x1, y1, x2, y2 = box
    widths, heights = _line_metrics(draw, lines, font)
    gap = 1 if len(lines) > 1 else 0
    total_height = sum(heights) + gap * (len(lines) - 1)
    cursor_y = y1 + ((y2 - y1) - total_height) / 2
    for line, width, height in zip(lines, widths, heights):
        bounds = draw.textbbox((0, 0), line, font=font)
        x = x1 + ((x2 - x1) - width) / 2 - bounds[0]
        y = cursor_y - bounds[1]
        draw.text((x, y), line, font=font, fill=fill)
        cursor_y += height + gap


def _truncate_to_width(draw, text, font, max_width):
    suffix = "…"
    suffix_bounds = draw.textbbox((0, 0), suffix, font=font)
    if suffix_bounds[2] - suffix_bounds[0] > max_width:
        return ""
    candidate = str(text or "")
    while candidate:
        shown = candidate + suffix
        bounds = draw.textbbox((0, 0), shown, font=font)
        if bounds[2] - bounds[0] <= max_width:
            return shown
        candidate = candidate[:-1]
    return suffix


def _draw_centered_single_line(
    draw, box, text, preferred=12, minimum=8, fill=1
):
    text = str(text or "").strip()
    if not text:
        return
    x1, y1, x2, y2 = box
    max_width = max(1, x2 - x1 - 4)
    max_height = max(1, y2 - y1 - 2)
    font = _fit_font(
        draw,
        text,
        max_width,
        max_height,
        preferred=preferred,
        minimum=minimum,
    )
    bounds = draw.textbbox((0, 0), text, font=font)
    if bounds[2] - bounds[0] > max_width:
        text = _truncate_to_width(draw, text, font, max_width)
    _draw_centered_lines(draw, box, [text], font, fill=fill)


def _draw_centered_club_name(
    draw, box, text, preferred=16, minimum=8, fill=1
):
    text = str(text or "").strip()
    if not text:
        return
    x1, y1, x2, y2 = box
    max_width = max(1, x2 - x1 - 4)
    max_height = max(1, y2 - y1 - 2)

    for size in range(preferred, max(10, minimum) - 1, -1):
        font = _load_font(size)
        widths, heights = _line_metrics(draw, [text], font)
        if widths[0] <= max_width and heights[0] <= max_height:
            _draw_centered_lines(draw, box, [text], font, fill=fill)
            return

    wrapped = split_club_name(text)
    if len(wrapped) == 2:
        for size in range(preferred, minimum - 1, -1):
            font = _load_font(size)
            widths, heights = _line_metrics(draw, wrapped, font)
            if max(widths) <= max_width and sum(heights) + 1 <= max_height:
                _draw_centered_lines(draw, box, wrapped, font, fill=fill)
                return

    font = _load_font(minimum)
    shown = _truncate_to_width(draw, text, font, max_width)
    _draw_centered_lines(draw, box, [shown], font, fill=fill)


def _draw_title(draw, title, box, fill=1):
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
            fill=fill,
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
    color_mode="single",
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

    color_mode = normalize_color_mode(color_mode)
    layout_color = LED_RED if color_mode == "double" else 1
    image_mode = "RGB" if color_mode == "double" else "1"
    background = LED_BLACK if color_mode == "double" else 0
    for page_index, page in enumerate(layout.pages, start=1):
        image = Image.new(image_mode, (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=layout_color)

        if show_title:
            draw.line((title_width, 0, title_width, height), fill=layout_color)
            _draw_title(
                draw, school_title, (0, 0, title_width, height), fill=layout_color
            )

        for region_index in range(region_count):
            rows = page.regions[region_index] if region_index < len(page.regions) else []
            region_x1 = round(title_width + region_width * region_index)
            region_x2 = round(title_width + region_width * (region_index + 1))
            if region_index:
                draw.line((region_x1, 0, region_x1, height), fill=layout_color)
            grade_width = min(
                90,
                max(1, int((region_x2 - region_x1) * 0.18)),
            )
            data_x1 = region_x1 + grade_width
            draw.line((data_x1, 0, data_x1, height), fill=layout_color)
            draw.line(
                (region_x1, header_height, region_x2, header_height),
                fill=layout_color,
            )

            region_columns = max((len(row.classes) for row in rows), default=1)
            class_width = max(1, (region_x2 - data_x1) / region_columns)
            for column in range(1, region_columns):
                x = round(data_x1 + class_width * column)
                draw.line((x, 0, x, height), fill=layout_color)
            for row_index in range(1, rows_per_region):
                y = header_height * (row_index + 1)
                draw.line((region_x1, y, region_x2, y), fill=layout_color)

            for column in range(region_columns):
                x1 = round(data_x1 + class_width * column)
                x2 = round(data_x1 + class_width * (column + 1))
                header = "状态" if int(class_type or 1) == 2 else f"{column + 1}班"
                _draw_centered(
                    draw, (x1, 0, x2, header_height), header,
                    preferred=18, fill=layout_color,
                )

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
                    fill=layout_color,
                )
                for column, item in enumerate(row.classes):
                    x1 = round(data_x1 + class_width * column)
                    x2 = round(data_x1 + class_width * (column + 1))
                    raw_status = _status_for(statuses, item)
                    _draw_centered(
                        draw,
                        (x1, y1, x2, y2),
                        display_status(raw_status, color_mode),
                        preferred=18,
                        fill=status_color(raw_status, color_mode),
                    )

        path = output_dir / f"{filename_prefix}-{page_index:02d}.bmp"
        image.save(path, format="BMP")
        paths.append(path)

    return paths


def render_club_led_pages(
    school_title,
    classes,
    statuses,
    output_dir,
    width=1024,
    height=96,
    rows_per_group=4,
    groups_per_page=5,
    show_title=True,
    filename_prefix="led-club-page",
    color_mode="single",
):
    row_count = max(1, int(rows_per_group))
    group_count = max(1, int(groups_per_page))
    layout = build_led_page_layout(
        classes,
        grades_per_page=row_count,
        regions_per_page=group_count,
        class_type=2,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob(f"{filename_prefix}-*.bmp"):
        stale.unlink()
    if not layout.pages:
        return []

    title_width = min(170, max(1, width // 7)) if show_title else 0
    content_width = width - title_width
    group_width = content_width / group_count
    header_height = max(1, height // (row_count + 1))
    paths = []

    color_mode = normalize_color_mode(color_mode)
    layout_color = LED_RED if color_mode == "double" else 1
    image_mode = "RGB" if color_mode == "double" else "1"
    background = LED_BLACK if color_mode == "double" else 0
    for page_index, page in enumerate(layout.pages, start=1):
        image = Image.new(image_mode, (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=layout_color)
        if show_title:
            draw.line((title_width, 0, title_width, height), fill=layout_color)
            _draw_title(
                draw, school_title, (0, 0, title_width, height), fill=layout_color
            )

        for group_index in range(group_count):
            rows = page.regions[group_index] if group_index < len(page.regions) else []
            group_x1 = round(title_width + group_width * group_index)
            group_x2 = round(title_width + group_width * (group_index + 1))
            if group_index:
                draw.line((group_x1, 0, group_x1, height), fill=layout_color)
            actual_group_width = max(2, group_x2 - group_x1)
            name_width, _ = calculate_club_column_widths(actual_group_width)
            status_x1 = group_x1 + name_width
            draw.line((status_x1, 0, status_x1, height), fill=layout_color)
            draw.line(
                (group_x1, header_height, group_x2, header_height),
                fill=layout_color,
            )
            for row_index in range(1, row_count):
                y = header_height * (row_index + 1)
                draw.line((group_x1, y, group_x2, y), fill=layout_color)

            _draw_centered(
                draw,
                (group_x1, 0, status_x1, header_height),
                "社团名",
                preferred=14,
                fill=layout_color,
            )
            _draw_centered_single_line(
                draw,
                (status_x1, 0, group_x2, header_height),
                "状态",
                preferred=14,
                fill=layout_color,
            )

            for row_index, row in enumerate(rows):
                y1 = header_height * (row_index + 1)
                y2 = header_height * (row_index + 2) if row_index < row_count - 1 else height
                item = row.classes[0]
                _draw_centered_club_name(
                    draw,
                    (group_x1, y1, status_x1, y2),
                    row.grade_name,
                    fill=layout_color,
                )
                raw_status = _status_for(statuses, item)
                _draw_centered_single_line(
                    draw,
                    (status_x1, y1, group_x2, y2),
                    display_status(raw_status, color_mode),
                    preferred=12,
                    fill=status_color(raw_status, color_mode),
                )

        path = output_dir / f"{filename_prefix}-{page_index:02d}.bmp"
        image.save(path, format="BMP")
        paths.append(path)
    return paths
