from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_PADDING_X = 30
_HEADER_HEIGHT = 80

_font_cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Find a TrueType font across project bundle, Windows, and Linux paths."""
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]

    suffix = "-Bold.ttf" if bold else ".ttf"
    candidates = [
        _FONTS_DIR / f"DejaVuSans{suffix}",
        Path(r"C:\Windows\Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path(r"C:\Windows\Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / f"DejaVuSans{suffix}",
    ]
    for path in candidates:
        try:
            if path.exists():
                font = ImageFont.truetype(str(path), size)
                _font_cache[key] = font
                return font
        except OSError:
            continue

    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def render_dashboard(
    interview_task: dict | None,
    interview_completed: bool,
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    today_label: str,
) -> Image.Image:
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    _draw_header(draw, today_label, width)

    available = height - _HEADER_HEIGHT
    has_birthdays = bool(birthdays)
    birthday_h = 130 if has_birthdays else 0
    main_h = (available - birthday_h) // 2

    y = _HEADER_HEIGHT
    _draw_task_section(draw, y, main_h, width, "INTERVIEW PREP",
                       _format_interview(interview_task), interview_completed)
    y += main_h
    _draw_task_section(draw, y, main_h, width, "RUNNING",
                       _format_run(run), run_completed)
    y += main_h
    if has_birthdays:
        _draw_birthdays_section(draw, y, birthday_h, width, birthdays)

    return img


def _draw_header(draw: ImageDraw.ImageDraw, label: str, width: int) -> None:
    draw.text((_PADDING_X, 18), label, font=_font(34, bold=True), fill=0)
    draw.line(
        [(_PADDING_X, _HEADER_HEIGHT - 2), (width - _PADDING_X, _HEADER_HEIGHT - 2)],
        fill=0, width=2,
    )


def _draw_task_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    height: int,
    width: int,
    label: str,
    content: dict | None,
    completed: bool,
) -> None:
    draw.text((_PADDING_X, y + 14), label, font=_font(14, bold=True), fill=100)

    if content and completed:
        _draw_done_badge(draw, width - _PADDING_X, y + 14)

    if not content:
        draw.text((_PADDING_X, y + 60), "Nothing planned for today",
                  font=_font(22), fill=140)
    else:
        draw.text((_PADDING_X, y + 44), content["title"],
                  font=_font(34, bold=True), fill=0)

        cursor_y = y + 88
        if content.get("subtitle"):
            draw.text((_PADDING_X, cursor_y), content["subtitle"],
                      font=_font(20), fill=70)
            cursor_y += 30

        if content.get("notes"):
            wrapped = _wrap_text(content["notes"], _font(16), width - 2 * _PADDING_X)
            for line in wrapped[:2]:
                draw.text((_PADDING_X, cursor_y), line, font=_font(16), fill=80)
                cursor_y += 22

    # Section separator (light gray)
    draw.line(
        [(_PADDING_X, y + height - 1), (width - _PADDING_X, y + height - 1)],
        fill=200, width=1,
    )


def _draw_done_badge(draw: ImageDraw.ImageDraw, right_x: int, top_y: int) -> None:
    text = "DONE"
    font = _font(14, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 10, 6
    box_w, box_h = text_w + 2 * pad_x, text_h + 2 * pad_y
    x0 = right_x - box_w
    y0 = top_y - 4
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=0)
    draw.text((x0 + pad_x, y0 + pad_y - bbox[1]), text, font=font, fill=255)


def _draw_birthdays_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    height: int,
    width: int,
    birthdays: list[dict],
) -> None:
    draw.text((_PADDING_X, y + 14), "BIRTHDAYS", font=_font(14, bold=True), fill=100)

    line_y = y + 44
    for bday in birthdays[:3]:
        days = bday.get("days_until", 0)
        if days == 0:
            when = "today"
        elif days == 1:
            when = "tomorrow"
        else:
            when = f"in {days} days"
        text = f"• {bday['name']} — {when}"
        draw.text((_PADDING_X, line_y), text,
                  font=_font(22, bold=days == 0), fill=0)
        line_y += 30


def _format_interview(task: dict | None) -> dict | None:
    if not task:
        return None
    type_labels = {
        "leetcode": "LeetCode",
        "system_design": "System Design",
        "behavioral": "Behavioral",
        "reading": "Reading",
    }
    raw_type = task.get("type", "")
    subtitle = type_labels.get(raw_type, raw_type.replace("_", " ").title())
    return {
        "title": task.get("task", "Unknown task"),
        "subtitle": subtitle,
        "notes": task.get("notes", ""),
    }


def _format_run(run: dict | None) -> dict | None:
    if not run:
        return None
    type_str = run.get("type", "rest")
    distance = run.get("distance_miles", 0)

    if type_str == "rest":
        return {"title": "Rest day", "subtitle": None, "notes": run.get("notes", "")}

    type_labels = {
        "easy": "Easy run",
        "workout": "Workout",
        "long": "Long run",
        "race": "Race",
        "other": "Run",
    }
    title = type_labels.get(type_str, type_str.title())
    subtitle = f"{distance} mi" if distance else None
    return {"title": title, "subtitle": subtitle, "notes": run.get("notes", "")}


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Greedy word-wrap by pixel width."""
    if not text:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in text.split():
        candidate = " ".join(current + [word])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def save_dashboard(img: Image.Image) -> Path:
    out = Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
