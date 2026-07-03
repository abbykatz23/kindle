import calendar
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

# --- Layout constants ---
PADDING_X = 40
TOP_PADDING = 30
INTERVIEW_SECTION_HEIGHT = 460
RUNNING_SECTION_HEIGHT = 300
BIRTHDAYS_SECTION_HEIGHT = 184  # 1024 - 30 - 460 - 300 - 50 footer
FOOTER_HEIGHT = 50

RIGHT_COL_X_START = Config.DASHBOARD_WIDTH // 2 + 10
INTERVIEW_TASKS_Y = TOP_PADDING + 70
TASK_LINE_HEIGHT = 55
CHECKBOX_SIZE = 28
MAX_TASKS_PER_SIDE = 7

MAX_BIRTHDAYS = 3

# Back button tap zone — used by tap_handler to detect "back" taps in detail views
BACK_BUTTON_MAX_X = 160
BACK_BUTTON_MAX_Y = 80

# Weekly detail view layout — used by tap_handler to map y → day row
WEEKLY_HEADER_Y = 78   # y where day rows begin
WEEKLY_ROW_H = 130     # height of each day row

# Interview day detail task list layout — used by tap_handler to map y → task row
TASK_LIST_START_Y = 168  # y where task rows begin in render_interview_day_detail
TASK_ROW_H = 55           # height of each task row

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
    interview_tasks: list[dict],
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    last_refreshed_label: str,
    run_feedback: str | None = None,
) -> Image.Image:
    """Each task dict needs `task` (name) and `completed` (bool)."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    y = TOP_PADDING
    _draw_interview_section(draw, y, width, interview_tasks)
    y += INTERVIEW_SECTION_HEIGHT

    _draw_running_section(draw, y, width, run, run_completed,
                          feedback=run_feedback,
                          show_bottom_divider=bool(birthdays))
    y += RUNNING_SECTION_HEIGHT

    if birthdays:
        _draw_birthdays_section(draw, y, width, birthdays)

    _draw_footer(draw, width, height, last_refreshed_label)

    return img


def _draw_interview_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    interview_tasks: list[dict],
) -> None:
    draw.text((PADDING_X, y + 14), "INTERVIEW PREP", font=_font(36, bold=True), fill=80)

    tasks_top = y + 70
    _draw_task_column(draw, PADDING_X, tasks_top, width - 2 * PADDING_X, interview_tasks)

    # Section separator
    draw.line(
        [(PADDING_X, y + INTERVIEW_SECTION_HEIGHT - 1),
         (width - PADDING_X, y + INTERVIEW_SECTION_HEIGHT - 1)],
        fill=80, width=2,
    )


def _draw_task_column(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_width: int,
    tasks: list[dict],
) -> None:
    if not tasks:
        draw.text((x, y), "—", font=_font(24), fill=160)
        return

    visible = tasks[:MAX_TASKS_PER_SIDE]
    overflow = len(tasks) - len(visible)
    title_font = _font(22)

    for i, task in enumerate(visible):
        line_y = y + i * TASK_LINE_HEIGHT
        _draw_checkbox(draw, x, line_y + 4, task.get("completed", False))

        text_x = x + CHECKBOX_SIZE + 12
        name = task.get("task", "")
        name = _truncate_to_width(name, title_font, max_width - (CHECKBOX_SIZE + 12))
        fill = 120 if task.get("completed") else 0
        draw.text((text_x, line_y + 4), name, font=title_font, fill=fill)

    if overflow > 0:
        line_y = y + len(visible) * TASK_LINE_HEIGHT
        draw.text((x, line_y + 4), f"+{overflow} more",
                  font=_font(18), fill=140)


def _draw_checkbox(draw: ImageDraw.ImageDraw, x: int, y: int, checked: bool) -> None:
    box = [x, y, x + CHECKBOX_SIZE, y + CHECKBOX_SIZE]
    if checked:
        draw.rectangle(box, fill=0)
        draw.line([(x + 6, y + CHECKBOX_SIZE // 2),
                   (x + CHECKBOX_SIZE // 2 - 1, y + CHECKBOX_SIZE - 7),
                   (x + CHECKBOX_SIZE - 5, y + 6)], fill=255, width=3)
    else:
        draw.rectangle(box, outline=0, width=2)


def _draw_running_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    run: dict | None,
    completed: bool,
    feedback: str | None = None,
    show_bottom_divider: bool = True,
) -> None:
    draw.text((PADDING_X, y + 22), "RUNNING", font=_font(36, bold=True), fill=80)

    if run and completed:
        _draw_done_badge(draw, width - PADDING_X, y + 22)
        if feedback:
            # Replace the plan details with the coaching note.
            # Try font sizes largest-first; shrink until the whole message fits in 3 lines.
            fb_font_size, fb_line_h = 24, 34
            for fs, lh in ((24, 34), (22, 31), (20, 28)):
                if len(_wrap_text(feedback, _font(fs), width - 2 * PADDING_X)) <= 3:
                    fb_font_size, fb_line_h = fs, lh
                    break
            wrapped = _wrap_text(feedback, _font(fb_font_size), width - 2 * PADDING_X)
            cursor_y = y + 82
            for line in wrapped[:3]:
                draw.text((PADDING_X, cursor_y), line, font=_font(fb_font_size), fill=50)
                cursor_y += fb_line_h
        else:
            # No feedback yet — show plan as-is
            formatted = _format_run(run)
            draw.text((PADDING_X, y + 70), formatted["title"], font=_font(54, bold=True), fill=0)
            cursor_y = y + 140
            if formatted.get("subtitle"):
                draw.text((PADDING_X, cursor_y), formatted["subtitle"], font=_font(30), fill=70)
                cursor_y += 44
            if formatted.get("notes"):
                wrapped = _wrap_text(formatted["notes"], _font(22), width - 2 * PADDING_X)
                for line in wrapped[:3]:
                    draw.text((PADDING_X, cursor_y), line, font=_font(22), fill=80)
                    cursor_y += 30
    elif not run:
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
            for line in wrapped[:3]:
                draw.text((PADDING_X, cursor_y), line, font=_font(22), fill=80)
                cursor_y += 30

    if show_bottom_divider:
        draw.line(
            [(PADDING_X, y + RUNNING_SECTION_HEIGHT - 1),
             (width - PADDING_X, y + RUNNING_SECTION_HEIGHT - 1)],
            fill=80, width=2,
        )


def _draw_done_badge(draw: ImageDraw.ImageDraw, right_x: int, top_y: int) -> None:
    text = "DONE"
    font = _font(24, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 10
    box_w, box_h = text_w + 2 * pad_x, text_h + 2 * pad_y
    x0 = right_x - box_w
    y0 = top_y + 7
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=0)
    draw.text((x0 + pad_x, y0 + pad_y - bbox[1]), text, font=font, fill=255)


def _draw_birthdays_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    birthdays: list[dict],
) -> None:
    draw.text((PADDING_X, y + 14), "BIRTHDAYS", font=_font(36, bold=True), fill=80)

    line_y = y + 72
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
    # Timestamp — bottom right
    ts_font = _font(20)
    ts_text = f"Last refreshed: {label}"
    ts_bbox = draw.textbbox((0, 0), ts_text, font=ts_font)
    ts_w = ts_bbox[2] - ts_bbox[0]
    ts_x = width - PADDING_X - ts_w
    ts_y = height - 26
    draw.text((ts_x, ts_y), ts_text, font=ts_font, fill=130)

    # Refresh button — above timestamp, right-aligned
    btn_font = _font(22, bold=True)
    btn_text = "REFRESH"
    btn_bbox = draw.textbbox((0, 0), btn_text, font=btn_font)
    btn_w = btn_bbox[2] - btn_bbox[0]
    btn_h = btn_bbox[3] - btn_bbox[1]
    pad_x, pad_y = 16, 10
    box_w, box_h = btn_w + 2 * pad_x, btn_h + 2 * pad_y
    box_x = width - PADDING_X - box_w
    box_y = ts_y - box_h - 14
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], fill=255, outline=100, width=2)
    draw.text((box_x + pad_x, box_y + pad_y - btn_bbox[1]), btn_text, font=btn_font, fill=100)


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


def _draw_back_button(draw: ImageDraw.ImageDraw) -> None:
    """Draw a '← BACK' button in the top-left corner (same style as REFRESH)."""
    text = "← BACK"
    font = _font(22, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 10
    bx, by = 20, 15
    bw, bh = text_w + 2 * pad_x, text_h + 2 * pad_y
    draw.rectangle([bx, by, bx + bw, by + bh], fill=255, outline=100, width=2)
    draw.text((bx + pad_x, by + pad_y - bbox[1]), text, font=font, fill=100)


def render_running_detail(
    week_plan: dict,
    today: date,
    run_completed: bool,
) -> Image.Image:
    """Full-page Kindle view: this week's running plan, condensed one-line summary per day."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    # ── Header ───────────────────────────────────────────────────────────────
    _draw_back_button(draw)
    title = "THIS WEEK'S RUNS"
    title_font = _font(28, bold=True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) // 2, 18), title, font=title_font, fill=80)

    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    week_range = (
        f"{monday.strftime('%b')} {monday.day} – "
        f"{sunday.strftime('%b')} {sunday.day}"
    )
    range_font = _font(19)
    rb = draw.textbbox((0, 0), week_range, font=range_font)
    draw.text((width - PADDING_X - (rb[2] - rb[0]), 24), week_range, font=range_font, fill=130)

    draw.line([(PADDING_X, WEEKLY_HEADER_Y - 10), (width - PADDING_X, WEEKLY_HEADER_Y - 10)],
              fill=80, width=2)

    if not week_plan:
        draw.text((PADDING_X, 120), "No active running plan.", font=_font(28), fill=130)
        return img

    # ── Day rows (condensed: day label + one summary line, tap to see full detail) ───────────
    DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    DAY_ABBREVS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    for i, (day_name, abbrev) in enumerate(zip(DAY_NAMES, DAY_ABBREVS)):
        row_y = WEEKLY_HEADER_Y + i * WEEKLY_ROW_H
        row_date = monday + timedelta(days=i)
        is_today = row_date == today
        run = week_plan.get(day_name)

        if is_today:
            draw.rectangle(
                [PADDING_X - 8, row_y + 2, width - PADDING_X + 8, row_y + WEEKLY_ROW_H - 3],
                outline=60, width=2,
            )

        label = f"{abbrev}  {row_date.strftime('%b')} {row_date.day}"
        if is_today:
            label += "  ·  TODAY"
        draw.text((PADDING_X, row_y + 10), label, font=_font(24, bold=True), fill=0)

        if is_today and run and run_completed:
            _draw_done_badge(draw, width - PADDING_X, row_y + 10)

        if run:
            formatted = _format_run(run)
            summary = formatted["title"]
            if formatted.get("subtitle"):
                summary += f"  ·  {formatted['subtitle']}"
            draw.text((PADDING_X, row_y + 52), summary, font=_font(22), fill=40)
        else:
            draw.text((PADDING_X, row_y + 52), "—", font=_font(22), fill=130)

        if i < 6:
            draw.line(
                [(PADDING_X, row_y + WEEKLY_ROW_H - 1),
                 (width - PADDING_X, row_y + WEEKLY_ROW_H - 1)],
                fill=140, width=1,
            )

    return img


def render_interview_detail(
    interview_tasks: list[dict],
    today: date,
) -> Image.Image:
    """Full-page Kindle view: this week's tasks, condensed one-line summary per day."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    # ── Header ───────────────────────────────────────────────────────────────
    _draw_back_button(draw)
    title = "THIS WEEK'S TASKS"
    title_font = _font(28, bold=True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) // 2, 18), title, font=title_font, fill=80)
    draw.line([(PADDING_X, WEEKLY_HEADER_Y - 10), (width - PADDING_X, WEEKLY_HEADER_Y - 10)],
              fill=80, width=2)

    # ── Group tasks by date ───────────────────────────────────────────────────
    monday = today - timedelta(days=today.weekday())
    day_buckets: dict[str, list[dict]] = {}
    for i in range(7):
        day_buckets[(monday + timedelta(days=i)).isoformat()] = []
    for task in interview_tasks:
        key = task.get("date", "")
        if key in day_buckets:
            day_buckets[key].append(task)

    DAY_ABBREVS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    for i, abbrev in enumerate(DAY_ABBREVS):
        row_date = monday + timedelta(days=i)
        row_y = WEEKLY_HEADER_Y + i * WEEKLY_ROW_H
        is_today = row_date == today
        tasks = day_buckets.get(row_date.isoformat(), [])

        if is_today:
            draw.rectangle(
                [PADDING_X - 8, row_y + 2, width - PADDING_X + 8, row_y + WEEKLY_ROW_H - 3],
                outline=60, width=2,
            )

        label = f"{abbrev}  {row_date.strftime('%b')} {row_date.day}"
        if is_today:
            label += "  ·  TODAY"
        draw.text((PADDING_X, row_y + 10), label, font=_font(24, bold=True), fill=0)

        summary = _interview_day_summary(tasks, width - 2 * PADDING_X)
        draw.text((PADDING_X, row_y + 52), summary, font=_font(22),
                  fill=40 if tasks else 130)

        if i < 6:
            draw.line(
                [(PADDING_X, row_y + WEEKLY_ROW_H - 1),
                 (width - PADDING_X, row_y + WEEKLY_ROW_H - 1)],
                fill=140, width=1,
            )

    return img


def render_birthdays_detail(
    all_birthdays: list[dict],
    today: date,
) -> Image.Image:
    """Full-page Kindle view: every registered birthday in two columns."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    # ── Header ───────────────────────────────────────────────────────────────
    _draw_back_button(draw)
    title = "ALL BIRTHDAYS"
    title_font = _font(28, bold=True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) // 2, 18), title, font=title_font, fill=80)
    draw.line([(PADDING_X, 68), (width - PADDING_X, 68)], fill=80, width=2)

    if not all_birthdays:
        draw.text((PADDING_X, 120), "No birthdays registered.", font=_font(28), fill=130)
        return img

    # Sort chronologically by MM-DD
    sorted_bdays = sorted(all_birthdays, key=lambda b: b["date"])

    # Find upcoming birthdays (within 7 days) to highlight
    upcoming_names: set[str] = set()
    for entry in sorted_bdays:
        try:
            month, day = map(int, entry["date"].split("-"))
            if month == 2 and day == 29 and not calendar.isleap(today.year):
                bday = today.replace(month=3, day=1)
            else:
                bday = today.replace(month=month, day=day)
            if 0 <= (bday - today).days <= 7:
                upcoming_names.add(entry["name"])
        except (ValueError, OverflowError):
            pass

    MONTH_ABBREVS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ENTRY_H = 33
    col_w = (width - 2 * PADDING_X) // 2
    start_y = 78

    mid = (len(sorted_bdays) + 1) // 2
    columns = [sorted_bdays[:mid], sorted_bdays[mid:]]

    for col_idx, entries in enumerate(columns):
        col_x = PADDING_X + col_idx * col_w
        date_right_x = col_x + col_w - 8  # right-align dates within this column

        for row_idx, entry in enumerate(entries):
            ey = start_y + row_idx * ENTRY_H
            if ey + ENTRY_H > height - 10:
                break

            is_upcoming = entry["name"] in upcoming_names
            bold = is_upcoming
            fill = 0 if is_upcoming else 60

            try:
                month, day = map(int, entry["date"].split("-"))
                date_str = f"{MONTH_ABBREVS[month]} {day}"
            except (ValueError, IndexError):
                date_str = entry["date"]

            name_text = f"• {entry['name']}"
            max_name_w = col_w - 65
            name_text = _truncate_to_width(name_text, _font(20, bold=bold), max_name_w)
            draw.text((col_x, ey), name_text, font=_font(20, bold=bold), fill=fill)

            db = draw.textbbox((0, 0), date_str, font=_font(20, bold=bold))
            draw.text((date_right_x - (db[2] - db[0]), ey), date_str,
                      font=_font(20, bold=bold), fill=fill)

    return img


def _interview_day_summary(tasks: list[dict], max_width: int) -> str:
    if not tasks:
        return "—"
    names = [t.get("task", "task") for t in tasks]
    line = " · ".join(names)
    return _truncate_to_width(line, _font(22), max_width)


def render_running_day_detail(
    run: dict | None,
    selected_date: date,
    run_completed: bool,
) -> Image.Image:
    """Full-page Kindle view: detailed info for a single day's run."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    _draw_back_button(draw)

    day_label = f"{selected_date.strftime('%A')}, {selected_date.strftime('%B')} {selected_date.day}"
    draw.text((PADDING_X, 100), day_label, font=_font(30, bold=True), fill=0)
    draw.line([(PADDING_X, 148), (width - PADDING_X, 148)], fill=80, width=2)

    if run and run_completed:
        _draw_done_badge(draw, width - PADDING_X, 100)

    if not run:
        draw.text((PADDING_X, 180), "Nothing planned.", font=_font(34), fill=140)
        return img

    formatted = _format_run(run)
    draw.text((PADDING_X, 170), formatted["title"], font=_font(54, bold=True), fill=0)

    cursor_y = 242
    if formatted.get("subtitle"):
        draw.text((PADDING_X, cursor_y), formatted["subtitle"], font=_font(30), fill=70)
        cursor_y += 50

    if formatted.get("notes"):
        cursor_y += 10
        wrapped = _wrap_text(formatted["notes"], _font(24), width - 2 * PADDING_X)
        for line in wrapped:
            if cursor_y + 34 > height - 20:
                break
            draw.text((PADDING_X, cursor_y), line, font=_font(24), fill=60)
            cursor_y += 34

    return img


def render_interview_day_detail(
    tasks: list[dict],
    selected_date: date,
) -> Image.Image:
    """Full-page Kindle view: all tasks for a single day with checkboxes."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    _draw_back_button(draw)

    day_label = f"{selected_date.strftime('%A')}, {selected_date.strftime('%B')} {selected_date.day}"
    draw.text((PADDING_X, 100), day_label, font=_font(30, bold=True), fill=0)
    draw.line([(PADDING_X, 148), (width - PADDING_X, 148)], fill=80, width=2)

    if not tasks:
        draw.text((PADDING_X, 180), "No tasks planned.", font=_font(28), fill=130)
        return img

    task_font = _font(24)
    max_task_w = width - 2 * PADDING_X - CHECKBOX_SIZE - 14
    cursor_y = 168

    for task in tasks:
        if cursor_y + 55 > height - 20:
            break
        completed = task.get("completed", False)
        _draw_checkbox(draw, PADDING_X, cursor_y + 4, completed)
        name = _truncate_to_width(task.get("task", ""), task_font, max_task_w)
        draw.text((PADDING_X + CHECKBOX_SIZE + 14, cursor_y + 4), name,
                  font=task_font, fill=120 if completed else 0)
        cursor_y += 55

    return img


def save_dashboard(img: Image.Image) -> Path:
    out = Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
