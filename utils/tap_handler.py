"""Shared tap routing logic — used by both the Flask /tap endpoint and scheduler."""
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from config import Config
from dashboard.render import (
    BACK_BUTTON_MAX_X,
    BACK_BUTTON_MAX_Y,
    DASH_ARM_BTN_H,
    FOOTER_HEIGHT,
    LEARNING_DASH_ARM_Y,
    LEARNING_DASH_LIST_Y,
    LEARNING_DASH_ROW_H,
    LEARNING_HEADER_Y,
    LEARNING_ROW_H,
    LEARNING_SECTION_HEIGHT,
    LOG_BTN_H,
    RUNNING_SECTION_HEIGHT,
    TOP_PADDING,
    WEEK_NAV_BTN_Y0,
    WEEK_NAV_BTN_Y1,
    WEEKLY_HEADER_Y,
    WEEKLY_ROW_H,
    get_dash_arm_button_ranges,
    get_log_button_ranges,
    get_week_nav_button_ranges,
)
from utils.kindle_state import (
    get_pending_minutes,
    get_selected_date,
    get_view,
    get_week_offset,
    set_pending_minutes,
    set_view,
)
from utils.plan import get_plan_week_bounds

_PROJECT_ROOT = Path(__file__).parent.parent


def trigger_refresh() -> None:
    """Re-render the dashboard (or current detail view) locally, then push to the Kindle.

    Rendering happens synchronously (fast, no network) so callers — including the
    web preview's /tap endpoint — see the updated dashboard.png right away. The
    actual SSH push is slow (can take 10s of seconds) and is fired as a detached
    background process so it doesn't block the caller (e.g. the whole Flask dev
    server, which is single-threaded).
    """
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py"), "--no-push"],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )
    log_path = _PROJECT_ROOT / "logs" / "push.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as log_file:
        subprocess.Popen(
            [sys.executable, str(_PROJECT_ROOT / "main.py"), "--push-only"],
            cwd=str(_PROJECT_ROOT),
            stdout=log_file,
            stderr=log_file,
        )


def handle_tap(x: int, y: int) -> str:
    """Process a Kindle tap and return a human-readable result string."""
    view = get_view()

    # ── Running day detail: only back button ──────────────────────────────────
    if view == "running_day":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("running", week_offset=get_week_offset())
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> running"
        return f"Tap ({x},{y}) -> running_day tap -- ignored"

    # ── Learning detail: back button or +5/+15/+30 log tap ────────────────────
    if view == "learning":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("dashboard")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> dashboard"
        if y >= LEARNING_HEADER_Y:
            from utils.learning import get_loggable_rows
            from utils.time_log import log_time

            rows = get_loggable_rows(date.today())
            row_idx = (y - LEARNING_HEADER_Y) // LEARNING_ROW_H
            if 0 <= row_idx < len(rows):
                row_y = LEARNING_HEADER_Y + row_idx * LEARNING_ROW_H
                btn_y = row_y + (LEARNING_ROW_H - LOG_BTN_H) // 2
                if btn_y <= y <= btn_y + LOG_BTN_H:
                    (x0_5, x1_5), (x0_15, x1_15), (x0_30, x1_30) = get_log_button_ranges(Config.DASHBOARD_WIDTH)
                    row = rows[row_idx]
                    minutes = None
                    if x0_5 <= x <= x1_5:
                        minutes = 5
                    elif x0_15 <= x <= x1_15:
                        minutes = 15
                    elif x0_30 <= x <= x1_30:
                        minutes = 30
                    if minutes:
                        log_time(row["category"], minutes, item_id=row["item_id"])
                        _safe_refresh()
                        return f"Tap ({x},{y}) -> log +{minutes}m on {row['label']}"
        return f"Tap ({x},{y}) -> learning tap -- ignored"

    # ── Weekly detail view (running only): back goes to dashboard, nav buttons change
    #    which week is shown, row tap opens that day's detail ────────────────────────
    if view == "running":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("dashboard")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> dashboard"

        week_offset = get_week_offset()
        today = date.today()

        if WEEK_NAV_BTN_Y0 <= y <= WEEK_NAV_BTN_Y1:
            bounds = get_plan_week_bounds(today)
            has_prev = week_offset > 0
            has_next = bool(bounds) and (bounds[0] + week_offset) < bounds[1]
            (prev_x0, prev_x1), (next_x0, next_x1) = get_week_nav_button_ranges(Config.DASHBOARD_WIDTH)
            if has_prev and prev_x0 <= x <= prev_x1:
                set_view("running", week_offset=week_offset - 1)
                _safe_refresh()
                return f"Tap ({x},{y}) -> PREV WEEK -> offset {week_offset - 1}"
            if has_next and next_x0 <= x <= next_x1:
                set_view("running", week_offset=week_offset + 1)
                _safe_refresh()
                return f"Tap ({x},{y}) -> NEXT WEEK -> offset {week_offset + 1}"
            return f"Tap ({x},{y}) -> weekly nav tap -- ignored"

        if y >= WEEKLY_HEADER_Y:
            row_idx = (y - WEEKLY_HEADER_Y) // WEEKLY_ROW_H
            if 0 <= row_idx <= 6:
                monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
                selected = monday + timedelta(days=row_idx)
                set_view("running_day", selected.isoformat(), week_offset=week_offset)
                _safe_refresh()
                return f"Tap ({x},{y}) -> running day {selected.isoformat()}"
        return f"Tap ({x},{y}) -> weekly tap -- ignored"

    # ── Birthdays detail: only back ───────────────────────────────────────────
    if view == "birthdays":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("dashboard")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> dashboard"
        return f"Tap ({x},{y}) -> birthdays tap -- ignored"

    # ── Dashboard view ────────────────────────────────────────────────────────
    learning_top = TOP_PADDING
    learning_bottom = TOP_PADDING + LEARNING_SECTION_HEIGHT
    running_top = learning_bottom
    running_bottom = running_top + RUNNING_SECTION_HEIGHT
    birthdays_top = running_bottom
    birthdays_bottom = Config.DASHBOARD_HEIGHT - FOOTER_HEIGHT

    # Refresh button always wins (bottom-right corner)
    if x >= 560 and y >= 940:
        _safe_refresh()
        return f"Tap ({x},{y}) -> REFRESH button"

    if running_top <= y < running_bottom:
        set_view("running")
        _safe_refresh()
        return f"Tap ({x},{y}) -> RUNNING section -> running detail view"

    if learning_top <= y < learning_bottom:
        # 1. Shared "+5"/"+15"/"+30" arm buttons: tap to arm that amount (tap the
        #    same value again to un-arm). Nothing is logged until a row is tapped.
        arm_y0 = learning_top + LEARNING_DASH_ARM_Y
        arm_y1 = arm_y0 + DASH_ARM_BTN_H
        if arm_y0 <= y <= arm_y1:
            (x0_5, x1_5), (x0_15, x1_15), (x0_30, x1_30) = get_dash_arm_button_ranges(Config.DASHBOARD_WIDTH)
            tapped = None
            if x0_5 <= x <= x1_5:
                tapped = 5
            elif x0_15 <= x <= x1_15:
                tapped = 15
            elif x0_30 <= x <= x1_30:
                tapped = 30
            if tapped:
                new_value = None if get_pending_minutes() == tapped else tapped
                set_pending_minutes(new_value)
                _safe_refresh()
                return f"Tap ({x},{y}) -> {'armed' if new_value else 'un-armed'} {tapped}m"

        # 2. A row in the loggable list: apply the armed amount if one is set,
        #    otherwise drill into the full detail page (e.g. to reach overflow rows).
        list_top = learning_top + LEARNING_DASH_LIST_Y
        if y >= list_top:
            from utils.learning import get_loggable_rows

            rows = get_loggable_rows(date.today())
            row_idx = (y - list_top) // LEARNING_DASH_ROW_H
            if 0 <= row_idx < len(rows):
                pending = get_pending_minutes()
                row = rows[row_idx]
                if pending:
                    from utils.time_log import log_time
                    log_time(row["category"], pending, item_id=row["item_id"])
                    set_pending_minutes(None)
                    _safe_refresh()
                    return f"Tap ({x},{y}) -> log +{pending}m on {row['label']}"
                set_view("learning")
                _safe_refresh()
                return f"Tap ({x},{y}) -> PROJECTS row -> learning detail view"

        # 3. Anywhere else in the section: a stray tap while armed just cancels
        #    (safer than jumping to a different screen on e-ink); otherwise drill in.
        if get_pending_minutes():
            set_pending_minutes(None)
            _safe_refresh()
            return f"Tap ({x},{y}) -> cancelled pending log"
        set_view("learning")
        _safe_refresh()
        return f"Tap ({x},{y}) -> PROJECTS section -> learning detail view"

    if birthdays_top <= y < birthdays_bottom:
        set_view("birthdays")
        _safe_refresh()
        return f"Tap ({x},{y}) -> BIRTHDAYS section -> birthdays detail view"

    return f"Tap ({x},{y}) -> outside sections -- ignored"


def _safe_refresh() -> None:
    try:
        trigger_refresh()
    except Exception as e:
        print(f"refresh failed: {e}", file=sys.stderr)
