from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

# --- Layout constants ---
PADDING_X = 40
TOP_PADDING = 30
INTERVIEW_SECTION_HEIGHT = 480
RUNNING_SECTION_HEIGHT = 280
BIRTHDAYS_SECTION_HEIGHT = 184  # 1024 - 30 - 480 - 280 - 50 footer
FOOTER_HEIGHT = 50

# Week-view layout (used by both renderer and tap handler if/when we map taps to days)
INTERVIEW_ROWS_Y_START = TOP_PADDING + 56  # under the "INTERVIEW PREP" label
DAY_ROW_HEIGHT = 58
DAY_LABEL_WIDTH = 64
TASK_GAP = 12
CHECKBOX_SIZE = 24

MAX_BIRTHDAYS = 3

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_font_cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
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
    week_tasks: dict[str, list[dict]],
    today: date,
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    last_refreshed_label: str,
) -> Image.Image:
    """
    week_tasks: dict mapping ISO date string (YYYY-MM-DD) to a list of task dicts for that day.
                Each task dict has at minimum `type`, `task`, `completed`.
    today:      today's date, used to highlight the current row.
    """
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    y = TOP_PADDING
    _draw_interview_week(draw, y, width, week_tasks, today)
    y += INTERVIEW_SECTION_HEIGHT

    _draw_running_section(draw, y, width, run, run_completed)
    y += RUNNING_SECTION_HEIGHT

    if birthdays:
        _draw_birthdays_section(draw, y, width, birthdays)

    _draw_footer(draw, width, height, last_refreshed_label)

    return img


def _draw_interview_week(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    week_tasks: dict[str, list[dict]],
    today: date,
) -> None:
    draw.text((PADDING_X, y + 14), "INTERVIEW PREP", font=_font(24, bold=True), fill=80)

    monday = today - timedelta(days=today.weekday())

    for i in range(7):
        day = monday + timedelta(days=i)
        row_y = INTERVIEW_ROWS_Y_START + i * DAY_ROW_HEIGHT
        is_today = (day == today)
        is_past = (day < today)

        # Day label (e.g. "MON")
        label = day.strftime("%a").upper()
        label_fill = 0 if is_today else (140 if is_past else 60)
        draw.text((PADDING_X, row_y + 4),
                  label, font=_font(22, bold=is_today), fill=label_fill)

        # Today marker — small filled bar to the left of the label
        if is_today:
            draw.rectangle(
                [PADDING_X - 14, row_y + 6, PADDING_X - 8, row_y + 32],
                fill=0,
            )

        # Tasks for that day
        tasks = week_tasks.get(day.isoformat(), [])
        _draw_day_tasks(draw, PADDING_X + DAY_LABEL_WIDTH, row_y,
                        width - PADDING_X - (PADDING_X + DAY_LABEL_WIDTH),
                        tasks, is_past)

    # Section separator
    draw.line(
        [(PADDING_X, y + INTERVIEW_SECTION_HEIGHT - 1),
         (width - PADDING_X, y + INTERVIEW_SECTION_HEIGHT - 1)],
        fill=180, width=2,
    )


def _draw_day_tasks(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_width: int,
    tasks: list[dict],
    is_past: bool,
) -> None:
    if not tasks:
        draw.text((x, y + 4), "—", font=_font(20), fill=180)
        return

    cursor_x = x
    task_font = _font(20)
    for task in tasks:
        completed = task.get("completed", False)
        name = task.get("task", "")
        text_w = task_font.getbbox(name)[2] - task_font.getbbox(name)[0]
        item_w = CHECKBOX_SIZE + 8 + text_w + TASK_GAP

        # If this task wouldn't fit, truncate it inline and stop
        if cursor_x + item_w > x + max_width:
            ellipsis_w = task_font.getbbox("…")[2] - task_font.getbbox("…")[0]
            avail = (x + max_width) - cursor_x - CHECKBOX_SIZE - 8 - ellipsis_w
            if avail < 30:
                # Not enough room for any more tasks
                draw.text((cursor_x, y + 4), "…", font=task_font, fill=120)
                return
            name = _truncate_to_width(name, task_font, avail)

        _draw_checkbox(draw, cursor_x, y + 6, completed)
        text_fill = 0 if completed else (140 if is_past else 50)
        draw.text((cursor_x + CHECKBOX_SIZE + 8, y + 4), name,
                  font=task_font, fill=text_fill)
        cursor_x += item_w


def _draw_checkbox(draw: ImageDraw.ImageDraw, x: int, y: int, checked: bool) -> None:
    box = [x, y, x + CHECKBOX_SIZE, y + CHECKBOX_SIZE]
    if checked:
        draw.rectangle(box, fill=0)
        draw.line([(x + 5, y + CHECKBOX_SIZE // 2),
                   (x + CHECKBOX_SIZE // 2 - 1, y + CHECKBOX_SIZE - 6),
                   (x + CHECKBOX_SIZE - 4, y + 5)], fill=255, width=3)
    else:
        draw.rectangle(box, outline=0, width=2)


def _draw_running_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    run: dict | None,
    completed: bool,
) -> None:
    draw.text((PADDING_X, y + 22), "RUNNING", font=_font(24, bold=True), fill=80)

    if run and completed:
        _draw_done_badge(draw, width - PADDING_X, y + 22)

    if not run:
        draw.text((PADDING_X, y + 90), "Nothing planned for today",
                  font=_font(34), fill=140)
    else:
        formatted = _format_run(run)
        draw.text((PADDING_X, y + 70), formatted["title"], font=_font(54, bold=True), fill=0)
        cursor_y = y + 140
        if formatted.get("subtitle"):
            draw.text((PADDING_X, cursor_y), formatted["subtitle"],
                      font=_font(30), fill=70)
            cursor_y += 44
        if formatted.get("notes"):
            wrapped = _wrap_text(formatted["notes"], _font(22), width - 2 * PADDING_X)
            for line in wrapped[:2]:
                draw.text((PADDING_X, cursor_y), line, font=_font(22), fill=80)
                cursor_y += 30

    draw.line(
        [(PADDING_X, y + RUNNING_SECTION_HEIGHT - 1),
         (width - PADDING_X, y + RUNNING_SECTION_HEIGHT - 1)],
        fill=180, width=2,
    )


def _draw_done_badge(draw: ImageDraw.ImageDraw, right_x: int, top_y: int) -> None:
    text = "DONE"
    font = _font(24, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 10
    box_w, box_h = text_w + 2 * pad_x, text_h + 2 * pad_y
    x0 = right_x - box_w
    y0 = top_y - 6
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=0)
    draw.text((x0 + pad_x, y0 + pad_y - bbox[1]), text, font=font, fill=255)


def _draw_birthdays_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    birthdays: list[dict],
) -> None:
    draw.text((PADDING_X, y + 14), "BIRTHDAYS", font=_font(22, bold=True), fill=80)

    line_y = y + 56
    for bday in birthdays[:MAX_BIRTHDAYS]:
        days = bday.get("days_until", 0)
        if days == 0:
            when = "today"
        elif days == 1:
            when = "tomorrow"
        else:
            when = f"{days} days away"
        date_str = bday.get("formatted_date", "")
        text = f"• {bday['name']} — {date_str} ({when})"
        draw.text((PADDING_X, line_y), text,
                  font=_font(22, bold=days == 0), fill=0)
        line_y += 34


def _draw_footer(draw: ImageDraw.ImageDraw, width: int, height: int, label: str) -> None:
    font = _font(16)
    text = f"Last refreshed: {label}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = width - PADDING_X - text_w
    y = height - 28
    draw.text((x, y), text, font=font, fill=130)


def _format_run(run: dict) -> dict:
    type_str = run.get("type", "rest")
    distance = run.get("distance_miles", 0)
    if type_str == "rest":
        return {"title": "Rest day", "subtitle": None, "notes": run.get("notes", "")}
    type_labels = {
        "easy": "Easy run", "workout": "Workout", "long": "Long run",
        "race": "Race", "other": "Run",
    }
    title = type_labels.get(type_str, type_str.title())
    subtitle = f"{distance} mi" if distance else None
    return {"title": title, "subtitle": subtitle, "notes": run.get("notes", "")}


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in text.split():
        candidate = " ".join(current + [word])
        if font.getbbox(candidate)[2] - font.getbbox(candidate)[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _truncate_to_width(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_width:
        return text
    while text and font.getbbox(text + "…")[2] - font.getbbox(text + "…")[0] > max_width:
        text = text[:-1]
    return text + "…"


def save_dashboard(img: Image.Image) -> Path:
    out = Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
