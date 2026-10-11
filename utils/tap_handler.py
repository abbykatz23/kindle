"""Shared tap routing logic — used by both the Flask /tap endpoint and scheduler."""
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from config import Config
from dashboard.render import (
    BACK_BUTTON_MAX_X,
    BACK_BUTTON_MAX_Y,
    FOOTER_HEIGHT,
    RESERVED_SECTION_HEIGHT,
    RUNNING_SECTION_HEIGHT,
    TOP_PADDING,
    WEEK_NAV_BTN_Y0,
    WEEK_NAV_BTN_Y1,
    WEEKLY_HEADER_Y,
    WEEKLY_ROW_H,
    get_week_nav_button_ranges,
)
from utils.kindle_state import (
    get_view,
    get_week_offset,
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
    running_top = TOP_PADDING
    running_bottom = running_top + RUNNING_SECTION_HEIGHT
    birthdays_top = running_bottom + RESERVED_SECTION_HEIGHT
    birthdays_bottom = Config.DASHBOARD_HEIGHT - FOOTER_HEIGHT

    # Refresh button always wins (bottom-right corner)
    if x >= 560 and y >= 940:
        _safe_refresh()
        return f"Tap ({x},{y}) -> REFRESH button"

    if running_top <= y < running_bottom:
        set_view("running")
        _safe_refresh()
        return f"Tap ({x},{y}) -> RUNNING section -> running detail view"

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
