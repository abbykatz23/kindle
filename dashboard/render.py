import calendar
import math
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

# --- Layout constants ---
PADDING_X = 40
TOP_PADDING = 30
LEARNING_SECTION_HEIGHT = 360
RUNNING_SECTION_HEIGHT = 400
BIRTHDAYS_SECTION_HEIGHT = 184  # 1024 - 30 - 360 - 400 - 50 footer
FOOTER_HEIGHT = 50

# Max wrapped lines for the RUNNING section's coaching feedback text.
FB_MAX_LINES = 7

# Route map thumbnail — shown top-right of the home-screen RUNNING section
# when today's run is completed and has GPS data.
ROUTE_THUMB_W = 150
ROUTE_THUMB_H = 110
ROUTE_THUMB_GAP = 14

MAX_BIRTHDAYS = 3

# Back button tap zone — used by tap_handler to detect "back" taps in detail views
BACK_BUTTON_MAX_X = 160
BACK_BUTTON_MAX_Y = 80

# Weekly detail view layout — used by tap_handler to map y → day row
WEEKLY_HEADER_Y = 78   # y where day rows begin
WEEKLY_ROW_H = 130     # height of each day row

# Learning detail view layout — used by tap_handler to map y → loggable row
LEARNING_HEADER_Y = 110  # y where the tappable row list begins
LEARNING_ROW_H = 64      # height of each row
LOG_BTN_W = 68                 # width of a +5/+15/+30 tap button
LOG_BTN_H = 40                 # height of a +5/+15/+30 tap button
LOG_BTN_GAP = 10               # gap between adjacent buttons

# Learning dashboard summary layout — one shared "arm" control (+5/+15/+30)
# plus a compact list of every loggable row (same rows as the detail view). Tap
# a number to arm it, then tap a row to log that amount against it.
LEARNING_DASH_ARM_Y = 12      # y-offset from section top where the arm buttons sit
DASH_ARM_BTN_W = 56                 # width of a shared "+5"/"+15"/"+30" arm button
DASH_ARM_BTN_H = 36                 # height of a shared "+5"/"+15"/"+30" arm button
DASH_ARM_BTN_GAP = 8                # gap between adjacent arm buttons
LEARNING_DASH_SUBTITLE_Y = 58  # y-offset for the "LeetCode: N solved" subtitle
LEARNING_DASH_DIVIDER_Y = 88   # y-offset for the divider above the row list
LEARNING_DASH_LIST_Y = 98      # y-offset from section top where the row list begins
LEARNING_DASH_ROW_H = 44       # height of each compact dashboard row

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
    learning_rows: list[dict],
    pending_minutes: int | None,
    leetcode_today: dict,
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    last_refreshed_label: str,
    run_feedback: str | None = None,
    route: list[tuple[float, float]] | None = None,
    actual_run: dict | None = None,
) -> Image.Image:
    """learning_rows is utils.learning.get_loggable_rows()'s output;
    pending_minutes is utils.kindle_state.get_pending_minutes()'s output;
    leetcode_today is utils.leetcode_history.get_today()'s output;
    actual_run is integrations.intervals_api.get_todays_run_detail()'s output."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    y = TOP_PADDING
    _draw_learning_section(draw, y, width, learning_rows, leetcode_today, pending_minutes)
    y += LEARNING_SECTION_HEIGHT

    _draw_running_section(draw, y, width, run, run_completed,
                          feedback=run_feedback,
                          show_bottom_divider=bool(birthdays),
                          route=route,
                          actual_run=actual_run)
    y += RUNNING_SECTION_HEIGHT

    if birthdays:
        _draw_birthdays_section(draw, y, width, birthdays)

    _draw_footer(draw, width, height, last_refreshed_label)

    return img


def _draw_learning_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    rows: list[dict],
    leetcode_today: dict,
    pending_minutes: int | None,
) -> None:
    """Shared arm-then-tap flow: tap 5/15 to arm an amount, then tap a row to log
    it against that category/item. `rows` is the same list the detail view uses,
    so every book/project/wildcard item gets its own unambiguous tap target."""
    draw.text((PADDING_X, y + 14), "PROJECTS", font=_font(36, bold=True), fill=80)
    _draw_arm_buttons(draw, width, y + LEARNING_DASH_ARM_Y, pending_minutes)

    lc_count = (leetcode_today or {}).get("count", 0)
    draw.text((PADDING_X, y + LEARNING_DASH_SUBTITLE_Y), f"LeetCode: {lc_count} solved today",
              font=_font(18), fill=130)

    draw.line(
        [(PADDING_X, y + LEARNING_DASH_DIVIDER_Y), (width - PADDING_X, y + LEARNING_DASH_DIVIDER_Y)],
        fill=140, width=1,
    )

    row_font = _font(22)
    cursor_y = y + LEARNING_DASH_LIST_Y
    max_row_bottom = y + LEARNING_SECTION_HEIGHT - 16

    if not rows:
        draw.text((PADDING_X, cursor_y), "Nothing to log yet.", font=row_font, fill=160)
    else:
        visible_count = 0
        for row in rows:
            if cursor_y + LEARNING_DASH_ROW_H > max_row_bottom:
                break
            if row["today_minutes"] > 0:
                text = f"{row['label']} — {row['today_minutes']}m today"
            else:
                text = row["label"]
            text = _truncate_to_width(text, row_font, width - 2 * PADDING_X)
            draw.text((PADDING_X, cursor_y), text, font=row_font, fill=0)
            cursor_y += LEARNING_DASH_ROW_H
            visible_count += 1

        overflow = len(rows) - visible_count
        if overflow > 0:
            draw.text((PADDING_X, cursor_y), f"+{overflow} more — tap to see all",
                      font=_font(16), fill=140)

    # Section separator
    draw.line(
        [(PADDING_X, y + LEARNING_SECTION_HEIGHT - 1),
         (width - PADDING_X, y + LEARNING_SECTION_HEIGHT - 1)],
        fill=80, width=2,
    )


def get_dash_arm_button_ranges(width: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return ((x0,x1) for '+5', (x0,x1) for '+15', (x0,x1) for '+30'), right-aligned.

    Shared by _draw_arm_buttons and tap_handler so button geometry can never
    drift between what's drawn and what's tap-hit-tested.
    """
    btn30_x1 = width - PADDING_X
    btn30_x0 = btn30_x1 - DASH_ARM_BTN_W
    btn15_x1 = btn30_x0 - DASH_ARM_BTN_GAP
    btn15_x0 = btn15_x1 - DASH_ARM_BTN_W
    btn5_x1 = btn15_x0 - DASH_ARM_BTN_GAP
    btn5_x0 = btn5_x1 - DASH_ARM_BTN_W
    return (btn5_x0, btn5_x1), (btn15_x0, btn15_x1), (btn30_x0, btn30_x1)


def _draw_arm_buttons(draw: ImageDraw.ImageDraw, width: int, btn_y: int, pending_minutes: int | None) -> None:
    (x0_5, x1_5), (x0_15, x1_15), (x0_30, x1_30) = get_dash_arm_button_ranges(width)
    btn_font = _font(20, bold=True)

    for x0, x1, minutes, text in (
        (x0_5, x1_5, 5, "+5"), (x0_15, x1_15, 15, "+15"), (x0_30, x1_30, 30, "+30"),
    ):
        armed = pending_minutes == minutes
        draw.rectangle([x0, btn_y, x1, btn_y + DASH_ARM_BTN_H],
                       fill=(0 if armed else 255), outline=100, width=2)
        tb = draw.textbbox((0, 0), text, font=btn_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((x0 + (DASH_ARM_BTN_W - tw) // 2, btn_y + (DASH_ARM_BTN_H - th) // 2 - tb[1]),
                  text, font=btn_font, fill=(255 if armed else 100))


def _draw_plan_details(draw: ImageDraw.ImageDraw, y: int, text_width: int, run: dict) -> None:
    """Draw a not-yet-completed (or feedback-less) run's title/subtitle/notes, using
    all the room actually available in the RUNNING section before it runs into the
    birthdays section below. Most notes are short and render at the default size with
    room to spare; a longer, more explanatory note (e.g. a workout with real structure)
    shrinks its font just enough to fit in full rather than getting cut off.
    """
    formatted = _format_run(run)
    draw.text((PADDING_X, y + 70), formatted["title"], font=_font(54, bold=True), fill=0)
    cursor_y = y + 140
    if formatted.get("subtitle"):
        draw.text((PADDING_X, cursor_y), formatted["subtitle"], font=_font(30), fill=70)
        cursor_y += 44

    notes = formatted.get("notes")
    if not notes:
        return

    # Leave a few px of breathing room before the divider at y + RUNNING_SECTION_HEIGHT.
    max_bottom = y + RUNNING_SECTION_HEIGHT - 6
    notes_font_size, notes_line_h, max_lines = 22, 30, 1
    for fs, lh in ((22, 30), (20, 27), (18, 24)):
        lines_available = max(1, (max_bottom - cursor_y) // lh)
        if len(_wrap_text(notes, _font(fs), text_width)) <= lines_available:
            notes_font_size, notes_line_h, max_lines = fs, lh, lines_available
            break
        max_lines = lines_available  # keep shrinking; this is our fallback if nothing fits fully

    wrapped = _wrap_text(notes, _font(notes_font_size), text_width)
    for line in wrapped[:max_lines]:
        draw.text((PADDING_X, cursor_y), line, font=_font(notes_font_size), fill=80)
        cursor_y += notes_line_h


def _draw_running_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    run: dict | None,
    completed: bool,
    feedback: str | None = None,
    show_bottom_divider: bool = True,
    route: list[tuple[float, float]] | None = None,
    actual_run: dict | None = None,
) -> None:
    draw.text((PADDING_X, y + 22), "RUNNING", font=_font(36, bold=True), fill=80)

    if run and completed:
        _draw_done_badge(draw, width - PADDING_X, y + 22)

        has_map = bool(route) and len(route) >= 2
        text_width = width - 2 * PADDING_X
        if has_map:
            text_width -= ROUTE_THUMB_W + ROUTE_THUMB_GAP
            thumb_x0 = width - PADDING_X - ROUTE_THUMB_W
            thumb_y0 = y + 80
            _draw_route(draw, thumb_x0, thumb_y0, ROUTE_THUMB_W, ROUTE_THUMB_H, route)

        if feedback:
            # Replace the plan details with the coaching note — but always lead with
            # the actual distance and pace, so those numbers don't get lost in prose.
            cursor_y = y + 78
            fb_max_lines = FB_MAX_LINES
            if actual_run:
                dist_text = f"{actual_run.get('distance_miles', 0)} mi"
                draw.text((PADDING_X, cursor_y), dist_text, font=_font(40, bold=True), fill=0)
                cursor_y += 46
                pace_text = f"{actual_run.get('pace_per_mile', '?')}/mi avg pace"
                draw.text((PADDING_X, cursor_y), pace_text, font=_font(24), fill=70)
                cursor_y += 40
                fb_max_lines = FB_MAX_LINES - 2

            # Try font sizes largest-first; shrink until the whole message fits in fb_max_lines lines.
            fb_font_size, fb_line_h = 24, 34
            for fs, lh in ((24, 34), (22, 31), (20, 28)):
                if len(_wrap_text(feedback, _font(fs), text_width)) <= fb_max_lines:
                    fb_font_size, fb_line_h = fs, lh
                    break
            wrapped = _wrap_text(feedback, _font(fb_font_size), text_width)
            for line in wrapped[:fb_max_lines]:
                draw.text((PADDING_X, cursor_y), line, font=_font(fb_font_size), fill=50)
                cursor_y += fb_line_h
        else:
            # No feedback yet — show plan as-is
            _draw_plan_details(draw, y, text_width, run)
    elif not run:
        draw.text((PADDING_X, y + 90), "Nothing planned for today",
                  font=_font(34), fill=140)
    else:
        _draw_plan_details(draw, y, width - 2 * PADDING_X, run)

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

    todays_names = [b["name"] for b in birthdays if b.get("days_until", 0) == 0]
    if todays_names:
        text = f"{' & '.join(todays_names)}!"
        font = _font(64, bold=True)
        text = _truncate_to_width(text, font, width - 2 * PADDING_X)
        draw.text((PADDING_X, y + 78), text, font=font, fill=0)
        return

    line_y = y + 72
    for bday in birthdays[:MAX_BIRTHDAYS]:
        days = bday.get("days_until", 0)
        if days == 1:
            when = "tomorrow"
        else:
            when = f"{days} days away"
        date_str = bday.get("formatted_date", "")
        text = f"• {bday['name']} — {date_str} ({when})"
        draw.text((PADDING_X, line_y), text,
                  font=_font(22), fill=0)
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


def _project_route(
    points: list[tuple[float, float]], box_w: int, box_h: int, padding: int = 6
) -> list[tuple[float, float]]:
    """Project (lat, lng) points to pixel coords that fit within box_w x box_h.

    Uses an equirectangular correction (scale longitude by cos(avg_lat)) so the
    route's shape isn't horizontally stretched, then scales/centers to fit.
    """
    if len(points) < 2:
        return []
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    avg_lat_rad = math.radians(sum(lats) / len(lats))
    xs = [lng * math.cos(avg_lat_rad) for lng in lngs]
    ys = [-lat for lat in lats]  # invert so north ends up at the top of the box

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)

    avail_w = max(box_w - 2 * padding, 1)
    avail_h = max(box_h - 2 * padding, 1)
    scale = min(avail_w / span_x, avail_h / span_y)

    offset_x = padding + (avail_w - span_x * scale) / 2
    offset_y = padding + (avail_h - span_y * scale) / 2

    return [
        (offset_x + (x - min_x) * scale, offset_y + (y - min_y) * scale)
        for x, y in zip(xs, ys)
    ]


def _draw_route(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    box_w: int,
    box_h: int,
    points: list[tuple[float, float]],
    line_width: int = 3,
) -> None:
    """Draw a route line-map inside a box_w x box_h box anchored at (x0, y0).

    No-ops silently if there aren't enough GPS points (e.g. treadmill runs).
    """
    pixel_points = _project_route(points, box_w, box_h)
    if not pixel_points:
        return
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], outline=180, width=1)
    abs_points = [(x0 + px, y0 + py) for px, py in pixel_points]
    draw.line(abs_points, fill=0, width=line_width, joint="curve")
    start_x, start_y = abs_points[0]
    r = max(line_width, 3)
    draw.ellipse([start_x - r, start_y - r, start_x + r, start_y + r], fill=0)


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


def get_log_button_ranges(width: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return ((x0,x1) for +5, (x0,x1) for +15, (x0,x1) for +30), right-aligned within a row.

    Shared by _draw_log_buttons and tap_handler so button geometry can never
    drift between what's drawn and what's tap-hit-tested.
    """
    btn30_x1 = width - PADDING_X
    btn30_x0 = btn30_x1 - LOG_BTN_W
    btn15_x1 = btn30_x0 - LOG_BTN_GAP
    btn15_x0 = btn15_x1 - LOG_BTN_W
    btn5_x1 = btn15_x0 - LOG_BTN_GAP
    btn5_x0 = btn5_x1 - LOG_BTN_W
    return (btn5_x0, btn5_x1), (btn15_x0, btn15_x1), (btn30_x0, btn30_x1)


def render_learning_detail(
    rows: list[dict],
    leetcode_today: dict,
) -> Image.Image:
    """Full-page Kindle view: every loggable category/item with +5/+15/+30 tap targets.

    `rows` is utils.learning.get_loggable_rows()'s output, passed through
    by the caller — render.py stays pure-Pillow with no utils/integrations imports.
    """
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    # ── Header ───────────────────────────────────────────────────────────────
    _draw_back_button(draw)
    title = "PROJECTS TIME LOG"
    title_font = _font(28, bold=True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) // 2, 18), title, font=title_font, fill=80)

    lc_count = (leetcode_today or {}).get("count", 0)
    lc_text = f"LeetCode: {lc_count} solved today"
    lc_font = _font(19)
    lb = draw.textbbox((0, 0), lc_text, font=lc_font)
    draw.text((width - PADDING_X - (lb[2] - lb[0]), 56), lc_text, font=lc_font, fill=130)

    draw.line([(PADDING_X, LEARNING_HEADER_Y - 10), (width - PADDING_X, LEARNING_HEADER_Y - 10)],
              fill=80, width=2)

    if not rows:
        draw.text((PADDING_X, 130), "Nothing to log yet.", font=_font(28), fill=130)
        return img

    max_visible = max(0, (height - LEARNING_HEADER_Y - 30) // LEARNING_ROW_H)
    visible = rows[:max_visible]
    overflow = len(rows) - len(visible)

    for i, row in enumerate(visible):
        row_y = LEARNING_HEADER_Y + i * LEARNING_ROW_H
        _draw_log_row(draw, width, row_y, row)
        if i < len(visible) - 1:
            draw.line(
                [(PADDING_X, row_y + LEARNING_ROW_H - 1),
                 (width - PADDING_X, row_y + LEARNING_ROW_H - 1)],
                fill=140, width=1,
            )

    if overflow > 0:
        overflow_y = LEARNING_HEADER_Y + len(visible) * LEARNING_ROW_H + 10
        draw.text((PADDING_X, overflow_y), f"+{overflow} more — manage from the web dashboard",
                  font=_font(18), fill=140)

    return img


_ROW_CATEGORY_TAGS = {"books": "BOOK", "projects": "PROJECT", "wildcard": "OTHER"}


def _draw_log_row(draw: ImageDraw.ImageDraw, width: int, row_y: int, row: dict) -> None:
    tag = _ROW_CATEGORY_TAGS.get(row["category"])
    label = f"{tag} · {row['label']}" if tag else row["label"]

    label_font = _font(22)
    buttons_w = 3 * LOG_BTN_W + 2 * LOG_BTN_GAP
    max_label_w = width - 2 * PADDING_X - buttons_w - 20
    label = _truncate_to_width(label, label_font, max_label_w)
    draw.text((PADDING_X, row_y + 8), label, font=label_font, fill=0)

    if row.get("today_minutes", 0) > 0:
        today_text = f"{row['today_minutes']}m today"
        draw.text((PADDING_X, row_y + 36), today_text, font=_font(17), fill=130)

    _draw_log_buttons(draw, width, row_y)


def _draw_log_buttons(draw: ImageDraw.ImageDraw, width: int, row_y: int) -> None:
    (x0_5, x1_5), (x0_15, x1_15), (x0_30, x1_30) = get_log_button_ranges(width)
    btn_y = row_y + (LEARNING_ROW_H - LOG_BTN_H) // 2
    btn_font = _font(20, bold=True)

    for x0, x1, text in ((x0_5, x1_5, "+5"), (x0_15, x1_15, "+15"), (x0_30, x1_30, "+30")):
        draw.rectangle([x0, btn_y, x1, btn_y + LOG_BTN_H], fill=255, outline=100, width=2)
        tb = draw.textbbox((0, 0), text, font=btn_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((x0 + (LOG_BTN_W - tw) // 2, btn_y + (LOG_BTN_H - th) // 2 - tb[1]),
                  text, font=btn_font, fill=100)


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


def _draw_labeled_block(
    draw: ImageDraw.ImageDraw,
    cursor_y: int,
    max_bottom: int,
    text_width: int,
    label: str,
    text: str,
    label_size: int = 20,
    text_size: int = 24,
    line_h: int = 32,
) -> int:
    """Draw a small caption label followed by wrapped body text, starting at cursor_y.

    Stops (without drawing a partial label) once max_bottom is reached. Returns the
    new cursor_y so callers can stack multiple blocks.
    """
    if not text or cursor_y + label_size + line_h > max_bottom:
        return cursor_y
    cursor_y += 14
    draw.text((PADDING_X, cursor_y), label, font=_font(label_size, bold=True), fill=130)
    cursor_y += label_size + 8
    for line in _wrap_text(text, _font(text_size), text_width):
        if cursor_y + line_h > max_bottom:
            break
        draw.text((PADDING_X, cursor_y), line, font=_font(text_size), fill=30)
        cursor_y += line_h
    return cursor_y


def render_running_day_detail(
    run: dict | None,
    selected_date: date,
    run_completed: bool,
    route: list[tuple[float, float]] | None = None,
    actual: dict | None = None,
    feedback: str | None = None,
    notes_actual: str | None = None,
) -> Image.Image:
    """Full-page Kindle view: detailed info for a single day — the assigned run, what
    was actually run (distance/pace/time from intervals.icu), the coach's feedback
    note, and (if GPS data exists) a route map."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    text_width = width - 2 * PADDING_X

    _draw_back_button(draw)

    day_label = f"{selected_date.strftime('%A')}, {selected_date.strftime('%B')} {selected_date.day}"
    draw.text((PADDING_X, 100), day_label, font=_font(30, bold=True), fill=0)
    draw.line([(PADDING_X, 148), (width - PADDING_X, 148)], fill=80, width=2)

    if run and run_completed:
        _draw_done_badge(draw, width - PADDING_X, 100)

    if not run:
        draw.text((PADDING_X, 180), "Nothing planned.", font=_font(34), fill=140)
        cursor_y = 230
    else:
        formatted = _format_run(run)
        draw.text((PADDING_X, 170), formatted["title"], font=_font(48, bold=True), fill=0)

        cursor_y = 230
        if formatted.get("subtitle"):
            draw.text((PADDING_X, cursor_y), formatted["subtitle"], font=_font(28), fill=70)
            cursor_y += 44

        if formatted.get("notes"):
            cursor_y += 6
            for line in _wrap_text(formatted["notes"], _font(22), text_width):
                if cursor_y + 30 > height - 20:
                    break
                draw.text((PADDING_X, cursor_y), line, font=_font(22), fill=60)
                cursor_y += 30

    # Reserve room at the bottom for the map, so the text blocks above don't crowd it out.
    has_map = run_completed and bool(route) and len(route) >= 2
    max_bottom = height - 20 - (260 if has_map else 0)

    if actual:
        mins = int(actual.get("moving_time_s") or 0) // 60
        secs = int(actual.get("moving_time_s") or 0) % 60
        time_str = f" ({mins}:{secs:02d})" if actual.get("moving_time_s") else ""
        actual_text = (
            f"{actual.get('distance_miles', 0)} mi @ "
            f"{actual.get('pace_per_mile', '?')}/mi avg pace{time_str}"
        )
        cursor_y = _draw_labeled_block(draw, cursor_y, max_bottom, text_width, "ACTUAL", actual_text)

    if feedback:
        cursor_y = _draw_labeled_block(draw, cursor_y, max_bottom, text_width, "COACH'S NOTE", feedback)

    if notes_actual:
        cursor_y = _draw_labeled_block(draw, cursor_y, max_bottom, text_width, "POST-RUN NOTES", notes_actual)

    if has_map:
        map_y0 = max(cursor_y + 24, height - 20 - 260)
        map_h = height - 20 - map_y0
        if map_h > 100:
            _draw_route(draw, PADDING_X, map_y0, text_width, map_h, route, line_width=4)

    return img




def save_dashboard(img: Image.Image) -> Path:
    out = Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
