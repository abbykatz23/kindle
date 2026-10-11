import calendar
import math
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

# --- Layout constants ---
PADDING_X = 40
TOP_PADDING = 30
RUNNING_SECTION_HEIGHT = 480
# Intentionally blank band between RUNNING and BIRTHDAYS, held for a future section.
RESERVED_SECTION_HEIGHT = 280
BIRTHDAYS_SECTION_HEIGHT = 184  # 1024 - 30 - 480 - 280 - 50 footer
FOOTER_HEIGHT = 50

# Max wrapped lines for the RUNNING section's coaching feedback text.
FB_MAX_LINES = 9

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
WEEKLY_HEADER_Y = 148  # y where day rows begin
WEEKLY_ROW_H = 122     # height of each day row

# Weekly detail view — prev/next week nav buttons, one row below the title. Kept below
# BACK_BUTTON_MAX_Y so its generous back-button tap zone (top-left corner) never overlaps
# the PREV WEEK button, which would otherwise sit under the same x/y range.
WEEK_NAV_BTN_Y0 = 88          # top y of the nav button row
WEEK_NAV_BTN_H = 40           # height of a nav button
WEEK_NAV_BTN_Y1 = WEEK_NAV_BTN_Y0 + WEEK_NAV_BTN_H
WEEK_NAV_BTN_GAP = 20         # gap between the prev and next buttons

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
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    last_refreshed_label: str,
    run_feedback: str | None = None,
    route: list[tuple[float, float]] | None = None,
    actual_run: dict | None = None,
    running_mode: str = "plan",
    last_run: dict | None = None,
    last_run_route: list[tuple[float, float]] | None = None,
) -> Image.Image:
    """actual_run is integrations.intervals_api.get_todays_run_detail()'s output;
    running_mode is utils.running_mode.get_running_mode()'s output — in "last_run"
    mode the RUNNING section shows last_run (get_last_run()'s output) instead of the plan."""
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    y = TOP_PADDING

    if running_mode == "last_run":
        _draw_last_run_section(draw, y, width, last_run,
                               show_bottom_divider=bool(birthdays),
                               route=last_run_route)
    else:
        _draw_running_section(draw, y, width, run, run_completed,
                              feedback=run_feedback,
                              show_bottom_divider=bool(birthdays),
                              route=route,
                              actual_run=actual_run)
    y += RUNNING_SECTION_HEIGHT + RESERVED_SECTION_HEIGHT

    if birthdays:
        _draw_birthdays_section(draw, y, width, birthdays)

    _draw_footer(draw, width, height, last_refreshed_label)

    return img


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
        draw.text((PADDING_X, cursor_y), formatted["subtitle"], font=_font(34), fill=70)
        cursor_y += 50

    notes = formatted.get("notes")
    if not notes:
        return

    # Leave a few px of breathing room before the divider at y + RUNNING_SECTION_HEIGHT.
    max_bottom = y + RUNNING_SECTION_HEIGHT - 6
    notes_font_size, notes_line_h, max_lines = 26, 36, 1
    for fs, lh in ((26, 36), (24, 33), (22, 30)):
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
                draw.text((PADDING_X, cursor_y), dist_text, font=_font(44, bold=True), fill=0)
                cursor_y += 52
                pace_text = f"{actual_run.get('pace_per_mile', '?')}/mi avg pace"
                draw.text((PADDING_X, cursor_y), pace_text, font=_font(28), fill=70)
                cursor_y += 44
                fb_max_lines = FB_MAX_LINES - 2

            # Try font sizes largest-first; shrink until the whole message fits in fb_max_lines lines.
            fb_font_size, fb_line_h = 28, 39
            for fs, lh in ((28, 39), (26, 36), (24, 34)):
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


def _format_duration(total_s: int) -> str:
    """e.g. 3725 -> '1:02:05', 1450 -> '24:10'."""
    hours, rem = divmod(int(total_s), 3600)
    mins, secs = divmod(rem, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"


def _last_run_date_label(start_date_local: str, today: date) -> str:
    """e.g. 'Today, Sep 22', 'Yesterday, Sep 21', 'Sat, Sep 19'."""
    try:
        run_date = date.fromisoformat(start_date_local[:10])
    except ValueError:
        return ""
    if run_date == today:
        day = "Today"
    elif run_date == today - timedelta(days=1):
        day = "Yesterday"
    else:
        day = run_date.strftime("%a")
    return f"{day}, {run_date.strftime('%b')} {run_date.day}"


def _draw_last_run_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    width: int,
    last_run: dict | None,
    show_bottom_divider: bool = True,
    route: list[tuple[float, float]] | None = None,
) -> None:
    """RUNNING section in "last run" mode: just the stats (and map) of the most recent
    run — no plan, no coaching feedback."""
    draw.text((PADDING_X, y + 22), "LAST RUN", font=_font(36, bold=True), fill=80)

    if not last_run:
        draw.text((PADDING_X, y + 90), "No recent runs", font=_font(34), fill=140)
    else:
        date_label = _last_run_date_label(last_run.get("start_date_local", ""), date.today())
        if date_label:
            font = _font(28, bold=True)
            bbox = draw.textbbox((0, 0), date_label, font=font)
            draw.text((width - PADDING_X - (bbox[2] - bbox[0]), y + 28), date_label, font=font, fill=0)

        has_map = bool(route) and len(route) >= 2
        text_width = width - 2 * PADDING_X
        if has_map:
            map_w, map_h = 300, 290
            text_width -= map_w + ROUTE_THUMB_GAP
            _draw_route(draw, width - PADDING_X - map_w, y + 84, map_w, map_h, route, line_width=4)

        cursor_y = y + 84
        if last_run.get("name"):
            name = _truncate_to_width(last_run["name"], _font(28), text_width)
            draw.text((PADDING_X, cursor_y), name, font=_font(28), fill=70)
            cursor_y += 44

        draw.text((PADDING_X, cursor_y), f"{last_run.get('distance_miles', 0)} mi",
                  font=_font(60, bold=True), fill=0)
        cursor_y += 82

        stats = [f"{last_run.get('pace_per_mile', '?')}/mi avg pace"]
        if last_run.get("moving_time_s"):
            stats.append(f"{_format_duration(last_run['moving_time_s'])} moving time")
        if last_run.get("elevation_ft") is not None:
            stats.append(f"{last_run['elevation_ft']} ft elevation")
        if last_run.get("average_heartrate"):
            stats.append(f"{last_run['average_heartrate']} bpm avg HR")
        for stat in stats:
            draw.text((PADDING_X, cursor_y), _truncate_to_width(stat, _font(30), text_width),
                      font=_font(30), fill=40)
            cursor_y += 46

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


def get_week_nav_button_ranges(width: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return ((x0,x1) for PREV WEEK, (x0,x1) for NEXT WEEK), split evenly across the row.

    Shared by _draw_week_nav_buttons and tap_handler so button geometry can never
    drift between what's drawn and what's tap-hit-tested.
    """
    total_w = width - 2 * PADDING_X
    btn_w = (total_w - WEEK_NAV_BTN_GAP) // 2
    prev_x0 = PADDING_X
    prev_x1 = prev_x0 + btn_w
    next_x1 = width - PADDING_X
    next_x0 = next_x1 - btn_w
    return (prev_x0, prev_x1), (next_x0, next_x1)


def _draw_week_nav_buttons(draw: ImageDraw.ImageDraw, width: int, show_prev: bool, show_next: bool) -> None:
    (prev_x0, prev_x1), (next_x0, next_x1) = get_week_nav_button_ranges(width)
    font = _font(20, bold=True)

    if show_prev:
        draw.rectangle([prev_x0, WEEK_NAV_BTN_Y0, prev_x1, WEEK_NAV_BTN_Y1], fill=255, outline=100, width=2)
        text = "‹ PREV WEEK"
        tb = draw.textbbox((0, 0), text, font=font)
        tx = prev_x0 + ((prev_x1 - prev_x0) - (tb[2] - tb[0])) // 2
        draw.text((tx, WEEK_NAV_BTN_Y0 + (WEEK_NAV_BTN_H - (tb[3] - tb[1])) // 2 - tb[1]),
                  text, font=font, fill=70)

    if show_next:
        draw.rectangle([next_x0, WEEK_NAV_BTN_Y0, next_x1, WEEK_NAV_BTN_Y1], fill=255, outline=100, width=2)
        text = "NEXT WEEK ›"
        tb = draw.textbbox((0, 0), text, font=font)
        tx = next_x0 + ((next_x1 - next_x0) - (tb[2] - tb[0])) // 2
        draw.text((tx, WEEK_NAV_BTN_Y0 + (WEEK_NAV_BTN_H - (tb[3] - tb[1])) // 2 - tb[1]),
                  text, font=font, fill=70)


def render_running_detail(
    week_plan: dict,
    today: date,
    run_completed: bool,
    week_offset: int = 0,
    has_prev: bool = False,
    has_next: bool = False,
) -> Image.Image:
    """Full-page Kindle view: a week of the running plan, condensed one-line summary per day.

    week_offset=0 is the current week; week_offset=1 is next week, etc. has_prev/has_next
    control whether the PREV WEEK / NEXT WEEK nav buttons are drawn (the caller decides
    this from the active plan's bounds, since render.py stays pure-Pillow).
    """
    width, height = Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)

    # ── Header ───────────────────────────────────────────────────────────────
    _draw_back_button(draw)
    if week_offset == 0:
        title = "THIS WEEK'S RUNS"
    elif week_offset == 1:
        title = "NEXT WEEK'S RUNS"
    else:
        title = "WEEK'S RUNS"
    title_font = _font(28, bold=True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) // 2, 18), title, font=title_font, fill=80)

    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)
    week_range = (
        f"{monday.strftime('%b')} {monday.day} – "
        f"{sunday.strftime('%b')} {sunday.day}"
    )
    range_font = _font(19)
    rb = draw.textbbox((0, 0), week_range, font=range_font)
    draw.text((width - PADDING_X - (rb[2] - rb[0]), 24), week_range, font=range_font, fill=130)

    _draw_week_nav_buttons(draw, width, has_prev, has_next)

    draw.line([(PADDING_X, WEEKLY_HEADER_Y - 10), (width - PADDING_X, WEEKLY_HEADER_Y - 10)],
              fill=80, width=2)

    if not week_plan:
        draw.text((PADDING_X, WEEKLY_HEADER_Y + 20), "No runs planned for this week.", font=_font(28), fill=130)
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




def save_dashboard(img: Image.Image, out: Path | None = None) -> Path:
    out = out or Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
