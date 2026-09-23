from dataclasses import dataclass
from pathlib import Path
import os
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont


LED_RED = (255, 0, 0)
LED_YELLOW = (255, 255, 0)
LED_GREEN = (0, 255, 0)
LED_BLACK = (0, 0, 0)
STATUS_KEYS = ('未放学', '放学中', '已放学')
STATUS_COLORS = {'red': LED_RED, 'yellow': LED_YELLOW, 'green': LED_GREEN}
DEFAULT_STATUS_COLORS = {'未放学': 'yellow', '放学中': 'red', '已放学': 'green'}


def normalize_color_mode(value):
    return "double" if str(value or "").strip().lower() == "double" else "single"


def status_labels_for_mode(labels=None, color_mode="single"):
    defaults = {'未放学': '未放学' if normalize_color_mode(color_mode) == 'double' else '',
                '放学中': '放学中', '已放学': '已放学'}
    return {**defaults, **(labels or {})}


def display_status(status, color_mode="single", labels=None):
    status = str(status or "").strip()
    return status_labels_for_mode(labels, color_mode).get(status or '未放学', status)


def status_color(status, color_mode="single", colors=None):
    if normalize_color_mode(color_mode) != "double":
        return 1
    status = str(status or "").strip() or '未放学'
    names = {**DEFAULT_STATUS_COLORS, **(colors or {})}
    return STATUS_COLORS[names.get(status, 'yellow')]


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
    grade_pages=None,
):
    rows_per_region = max(1, int(grades_per_page))
    region_count = max(1, int(regions_per_page))
    rows = _build_rows(classes, class_type)
    max_columns = max((len(row.classes) for row in rows), default=0)
    if grade_pages and class_type == 1:
        by_grade = {row.grade_name: row for row in rows}
        pages = []
        for group in grade_pages:
            screen_rows = [by_grade[grade] for grade in group if grade in by_grade]
            if not screen_rows:
                continue
            region_size = max(1, (len(screen_rows) + region_count - 1) // region_count)
            regions = [screen_rows[index * region_size:(index + 1) * region_size]
                       for index in range(region_count)]
            pages.append(LedPage(regions=regions))
        return LedPageLayout(pages=pages, max_columns=max_columns)
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


def _fit_font(draw, text, max_width, max_height, preferred=20, minimum=1):
    preferred = max(1, int(preferred))
    minimum = max(1, min(preferred, int(minimum)))
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
    if text_width > x2 - x1 - 2 or text_height > y2 - y1 - 2:
        # Even a one-pixel font can exceed an extremely small cell. Never
        # paint a status into a neighbouring class or over its grid lines.
        return
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
    preferred = max(1, int(preferred))
    minimum = max(1, min(preferred, int(minimum)))

    for size in range(preferred, min(preferred, max(10, minimum)) - 1, -1):
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


def _draw_title(draw, title, box, fill=1, preferred=22, scale_percent=None):
    lines = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if not lines:
        return 0
    x1, y1, x2, y2 = box
    line_height = (y2 - y1) / len(lines)
    limit = max(1, int(min(x2 - x1 - 4, line_height - 2)))
    horizontal_fit = min(
        _fit_font(draw, line, max(1, x2 - x1 - 4),
                  max(1, int(line_height) - 2), preferred=limit).size
        for line in lines
    )
    if scale_percent is None:
        horizontal_size = min(preferred, horizontal_fit)
    else:
        horizontal_size = max(1, round(horizontal_fit * int(scale_percent) / 100))
    # A narrow LED side band cannot hold several Chinese characters on one
    # horizontal line. Stack them vertically when that yields larger glyphs.
    if x2 - x1 <= 64 and y2 - y1 > x2 - x1:
        columns = [list(line.replace(' ', '')) for line in lines]
        column_width = (x2 - x1) / len(columns)
        slot_height = min((y2 - y1) / len(chars) for chars in columns)
        vertical_limit = max(1, int(min(column_width - 2, slot_height - 2)))
        vertical_fit = min(
            _fit_font(draw, char, max(1, int(column_width) - 2),
                      max(1, int(slot_height) - 2), preferred=vertical_limit).size
            for chars in columns for char in chars
        )
        vertical_size = (min(preferred, vertical_fit) if scale_percent is None
                         else max(1, round(vertical_fit * int(scale_percent) / 100)))
        if vertical_size > horizontal_size:
            for column, chars in enumerate(columns):
                for index, char in enumerate(chars):
                    left = x1 + column * column_width
                    top = y1 + index * (y2 - y1) / len(chars)
                    _draw_centered(draw, (int(left), int(top),
                                          int(left + column_width),
                                          int(top + (y2 - y1) / len(chars))),
                                   char, preferred=vertical_size, fill=fill)
            return vertical_size
    preferred = horizontal_size
    for index, line in enumerate(lines):
        _draw_centered(
            draw,
            (x1, int(y1 + index * line_height), x2, int(y1 + (index + 1) * line_height)),
            line,
            preferred=preferred,
            fill=fill,
        )
    return preferred


def _status_for(statuses, item):
    class_id = str(item.get("class_id") or "")
    class_type = int(item.get("class_type") or 1)
    return statuses.get((class_type, class_id), statuses.get(class_id, ""))


def _class_header(item):
    """Use the supplied class identity, never the position in the catalog."""
    label = str(item.get("class_show_name") or item.get("class_name") or item.get("class_id") or "").strip()
    grade = str(item.get("grade_name") or "").strip()
    if grade and label.startswith(grade):
        label = label[len(grade):].strip()
    # Normalize known number formats, but keep named classes intact.
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", label))
    number = re.fullmatch(r"(?:\d+|[一二三四五六七八九十]+)[.·](\d+)班?", compact)
    if not number:
        number = re.search(r"\((\d+)\)班?$", compact)
    if not number:
        number = re.fullmatch(r"(\d+)班", compact)
    if number:
        return f"{int(number.group(1))}班"
    chinese = re.fullmatch(r"([一二三四五六七八九十]+)班", compact)
    if chinese:
        digits = {c: n for n, c in enumerate('零一二三四五六七八九')}
        text = chinese.group(1)
        if len(text) == 1 and text in digits:
            return f"{digits[text]}班"
        if text.count('十') == 1:
            tens, ones = text.split('十')
            if (not tens or tens in digits) and (not ones or ones in digits):
                return f"{digits.get(tens, 1) * 10 + digits.get(ones, 0)}班"
    return label


def _admin_headers(rows, class_type):
    headers = list(dict.fromkeys(
        "状态" if int(class_type or 1) == 2 else _class_header(item)
        for row in rows for item in row.classes
    ))
    numbered = sorted((h for h in headers if re.fullmatch(r"\d+班", h)),
                      key=lambda h: int(h[:-1]))
    return numbered + [h for h in headers if h not in numbered]


def _fit_admin_region(draw, rows, headers, width, height, header_size=0, cell_size=0,
                      status_texts=None, table_scale_percent=100):
    """Solve font sizes and grade-column width together, reserving room for statuses.

    Automatic row/column/status text shares one size. Explicit font sizes remain
    upper bounds, and the grade column follows measured text plus proportional padding.
    """
    row_height = max(1, height // (len(rows) + 1))
    automatic = max(1, int(row_height * 0.60))
    supplied = [int(v) for v in (header_size, cell_size) if v]
    base = min(supplied) if supplied else automatic
    header_start = int(header_size or base)
    cell_start = int(cell_size or base)
    grade_names = [row.grade_name for row in rows]
    for step in range(max(header_start, cell_start), 0, -1):
        factor = step / max(header_start, cell_start)
        hs, cs = max(1, int(header_start * factor)), max(1, int(cell_start * factor))
        hf, cf = _load_font(hs), _load_font(cs)
        padding = max(6, round(max(hs, cs) * 0.65))
        def dimensions(texts, font):
            boxes = [draw.textbbox((0, 0), text, font=font) for text in texts]
            return max((b[2]-b[0] for b in boxes), default=0), max((b[3]-b[1] for b in boxes), default=0)
        gw, gh = dimensions(grade_names, hf)
        hw, hh = dimensions(headers, hf)
        sw, sh = dimensions(status_texts or ['未放学', '放学中', '已放学'], cf)
        grade_width = gw + padding
        cell_width = max(hw, sw) + padding
        if grade_width + len(headers) * cell_width <= width and max(gh, hh, sh) + 4 <= row_height:
            if not supplied:
                # A percentage of the fitted maximum keeps the adjustment
                # responsive even when width, rather than row height, limits it.
                hs = cs = max(1, round(hs * table_scale_percent / 100))
                gw, _ = dimensions(grade_names, _load_font(hs))
                grade_width = gw + max(6, round(hs * 0.65))
            return hs, cs, grade_width
    # Extremely small LED viewports still reserve a nonzero data area; drawing
    # helpers skip any glyph that cannot fit rather than crossing a grid line.
    return 1, 1, max(1, min(width // 3, grade_width))


def _top_title_pages(renderer, options):
    """Render the table in its own viewport so no grid line crosses the title."""
    options = dict(options)
    title = options['school_title']
    width, height = options['width'], options['height']
    band = max(1, min(height - 1, height // 6))
    options.update(show_title=False, height=max(1, height - band), title_position='left')
    paths = renderer(**options)
    dual = normalize_color_mode(options['color_mode']) == 'double'
    color = LED_RED if dual else 1
    for path in paths:
        with Image.open(path) as table:
            image = Image.new(table.mode, (width, height), LED_BLACK if dual else 0)
            image.paste(table, (0, band))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=color)
        draw.line((0, band, width - 1, band), fill=color)
        title_size = _draw_title(draw, ' '.join(str(title).splitlines()),
                                 (0, 0, width, band), fill=color,
                                 preferred=int(options['title_font_size'] or 22 * options['pixel_scale']),
                                 scale_percent=(None if options['title_font_size'] else options['title_scale_percent']))
        if options.get('metrics') is not None:
            options['metrics'][len(options['metrics']) - len(paths) + paths.index(path)]['title_px'] = title_size
        image.save(path, format='BMP')
    return paths


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
    title_font_size=0,
    header_font_size=0,
    cell_font_size=0,
    title_position="left",
    pixel_scale=1.0,
    status_labels=None,
    status_colors=None,
    table_scale_percent=100,
    title_scale_percent=100,
    metrics=None,
    grade_pages=None,
):
    if show_title and title_position == "top":
        return _top_title_pages(render_led_pages, locals())
    rows_per_region = max(1, int(grades_per_page))
    region_count = max(1, int(regions_per_page))
    layout = build_led_page_layout(
        classes,
        grades_per_page=rows_per_region,
        regions_per_page=region_count,
        class_type=class_type,
        grade_pages=grade_pages,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob(f"{filename_prefix}-*.bmp"):
        stale.unlink()

    if not layout.pages:
        return []

    # Shrink labels on small contractor-provided screen sizes instead of
    # allowing their fixed minimums to consume the entire content area.
    title_width = min(round(170 * pixel_scale), max(1, width // 7)) if show_title else 0
    content_width = width - title_width
    region_width = content_width / region_count
    paths = []

    color_mode = normalize_color_mode(color_mode)
    layout_color = LED_RED if color_mode == "double" else 1
    image_mode = "RGB" if color_mode == "double" else "1"
    background = LED_BLACK if color_mode == "double" else 0
    title_preferred = int(title_font_size or 22 * pixel_scale)
    header_preferred = int(header_font_size or 18 * pixel_scale * table_scale_percent / 100)
    cell_preferred = int(cell_font_size or 18 * pixel_scale * table_scale_percent / 100)
    shown_statuses = list(status_labels_for_mode(status_labels, color_mode).values())
    for page_index, page in enumerate(layout.pages, start=1):
        image = Image.new(image_mode, (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=layout_color)

        if show_title:
            draw.line((title_width, 0, title_width, height), fill=layout_color)
            title_size = _draw_title(
                draw,
                school_title,
                (0, 0, title_width, height),
                fill=layout_color,
                preferred=title_preferred,
                scale_percent=(None if title_font_size else title_scale_percent),
            )

        region_metrics = [
            _fit_admin_region(draw, rows, _admin_headers(rows, class_type),
                              int(region_width), height, header_font_size, cell_font_size,
                              shown_statuses, table_scale_percent)
            for rows in page.regions if rows
        ]
        page_header_size = min((m[0] for m in region_metrics), default=1)
        page_cell_size = min((m[1] for m in region_metrics), default=1)
        if metrics is not None:
            metrics.append({'kind': 'admin', 'header_px': page_header_size,
                            'cell_px': page_cell_size,
                            'title_px': title_size if show_title else 0,
                            'row_count': max((len(rows) for rows in page.regions), default=0),
                            'column_count': max((len(_admin_headers(rows, class_type))
                                                 for rows in page.regions), default=0),
                            'max_status_chars': max(map(len, shown_statuses), default=0)})
        for region_index in range(region_count):
            rows = page.regions[region_index] if region_index < len(page.regions) else []
            actual_row_count = max(1, len(rows))
            header_height = max(1, height // (actual_row_count + 1))
            region_x1 = round(title_width + region_width * region_index)
            region_x2 = round(title_width + region_width * (region_index + 1))
            if region_index:
                draw.line((region_x1, 0, region_x1, height), fill=layout_color)
            if not rows:
                continue
            headers = _admin_headers(rows, class_type)
            header_preferred, cell_preferred, grade_width = _fit_admin_region(
                draw, rows, headers, region_x2 - region_x1, height,
                page_header_size, page_cell_size, shown_statuses,
            )
            data_x1 = region_x1 + grade_width
            draw.line((data_x1, 0, data_x1, height), fill=layout_color)
            draw.line(
                (region_x1, header_height, region_x2, header_height),
                fill=layout_color,
            )

            region_columns = len(headers)
            header_columns = {header: index for index, header in enumerate(headers)}
            class_width = max(1, (region_x2 - data_x1) / region_columns)
            for column in range(1, region_columns):
                x = round(data_x1 + class_width * column)
                draw.line((x, 0, x, height), fill=layout_color)
            for row_index in range(1, actual_row_count):
                y = header_height * (row_index + 1)
                draw.line((region_x1, y, region_x2, y), fill=layout_color)

            for column in range(region_columns):
                x1 = round(data_x1 + class_width * column)
                x2 = round(data_x1 + class_width * (column + 1))
                header = headers[column]
                _draw_centered(
                    draw, (x1, 0, x2, header_height), header,
                    preferred=header_preferred, fill=layout_color,
                )

            for row_index, row in enumerate(rows):
                y1 = header_height * (row_index + 1)
                y2 = (
                    header_height * (row_index + 2)
                    if row_index < len(rows) - 1
                    else height
                )
                _draw_centered(
                    draw,
                    (region_x1, y1, data_x1, y2),
                    row.grade_name,
                    preferred=header_preferred,
                    fill=layout_color,
                )
                for item in row.classes:
                    header = "状态" if int(class_type or 1) == 2 else _class_header(item)
                    column = header_columns[header]
                    x1 = round(data_x1 + class_width * column)
                    x2 = round(data_x1 + class_width * (column + 1))
                    raw_status = _status_for(statuses, item)
                    _draw_centered(
                        draw,
                        (x1, y1, x2, y2),
                        display_status(raw_status, color_mode, status_labels),
                        preferred=cell_preferred,
                        fill=status_color(raw_status, color_mode, status_colors),
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
    title_font_size=0,
    header_font_size=0,
    cell_font_size=0,
    title_position="left",
    pixel_scale=1.0,
    status_labels=None,
    status_colors=None,
    table_scale_percent=100,
    title_scale_percent=100,
    metrics=None,
):
    if show_title and title_position == "top":
        return _top_title_pages(render_club_led_pages, locals())
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

    title_width = min(round(170 * pixel_scale), max(1, width // 7)) if show_title else 0
    content_width = width - title_width
    group_width = content_width / group_count
    header_height = max(1, height // (row_count + 1))
    paths = []

    color_mode = normalize_color_mode(color_mode)
    layout_color = LED_RED if color_mode == "double" else 1
    image_mode = "RGB" if color_mode == "double" else "1"
    background = LED_BLACK if color_mode == "double" else 0
    title_preferred = int(title_font_size or 22 * pixel_scale)
    header_preferred = int(header_font_size or 14 * pixel_scale * table_scale_percent / 100)
    club_name_preferred = int(header_font_size or 16 * pixel_scale * table_scale_percent / 100)
    cell_preferred = int(cell_font_size or 12 * pixel_scale * table_scale_percent / 100)
    for page_index, page in enumerate(layout.pages, start=1):
        if not header_font_size and not cell_font_size:
            name_width, status_width = calculate_club_column_widths(int(group_width))
            limit = max(1, min(header_height - 2, name_width - 4, status_width - 4))
            fit_texts = [('社团名', name_width), ('状态', status_width)]
            for row in page.rows:
                fit_texts.extend((part, name_width) for part in split_club_name(row.grade_name))
                fit_texts.append((display_status(_status_for(statuses, row.classes[0]),
                                                 color_mode, status_labels), status_width))
            maximum = min(_fit_font(ImageDraw.Draw(Image.new(image_mode, (1, 1))),
                                    text or ' ', max(1, cell_width - 4),
                                    max(1, header_height - 2), preferred=limit).size
                          for text, cell_width in fit_texts)
            fitted = max(1, round(maximum * table_scale_percent / 100))
            header_preferred = club_name_preferred = cell_preferred = fitted
        if metrics is not None:
            metrics.append({'kind': 'club', 'header_px': header_preferred,
                            'cell_px': cell_preferred})
        image = Image.new(image_mode, (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=layout_color)
        if show_title:
            draw.line((title_width, 0, title_width, height), fill=layout_color)
            title_size = _draw_title(
                draw,
                school_title,
                (0, 0, title_width, height),
                fill=layout_color,
                preferred=title_preferred,
                scale_percent=(None if title_font_size else title_scale_percent),
            )
            if metrics is not None:
                metrics[-1]['title_px'] = title_size

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
                preferred=header_preferred,
                fill=layout_color,
            )
            _draw_centered_single_line(
                draw,
                (status_x1, 0, group_x2, header_height),
                "状态",
                preferred=header_preferred,
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
                    preferred=club_name_preferred,
                    fill=layout_color,
                )
                raw_status = _status_for(statuses, item)
                _draw_centered_single_line(
                    draw,
                    (status_x1, y1, group_x2, y2),
                    display_status(raw_status, color_mode, status_labels),
                    preferred=cell_preferred,
                    fill=status_color(raw_status, color_mode, status_colors),
                )

        path = output_dir / f"{filename_prefix}-{page_index:02d}.bmp"
        image.save(path, format="BMP")
        paths.append(path)
    return paths
