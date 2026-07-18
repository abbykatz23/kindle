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
    INTERVIEW_PREP_HEADER_Y,
    INTERVIEW_PREP_ROW_H,
    INTERVIEW_SECTION_HEIGHT,
    LOG_BTN_H,
    RUNNING_SECTION_HEIGHT,
    TOP_PADDING,
    WEEKLY_HEADER_Y,
    WEEKLY_ROW_H,
    get_log_button_ranges,
)
from utils.kindle_state import get_selected_date, get_view, set_view

_PROJECT_ROOT = Path(__file__).parent.parent


def trigger_refresh() -> None:
    """Re-render the dashboard (or current detail view) and push it to the Kindle."""
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py")],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )


def handle_tap(x: int, y: int) -> str:
    """Process a Kindle tap and return a human-readable result string."""
    view = get_view()

    # ── Running day detail: only back button ──────────────────────────────────
    if view == "running_day":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("running")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> running"
        return f"Tap ({x},{y}) -> running_day tap -- ignored"

    # ── Interview prep detail: back button or +15/+30 log tap ─────────────────
    if view == "interview_prep":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("dashboard")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> dashboard"
        if y >= INTERVIEW_PREP_HEADER_Y:
            from utils.interview_prep import get_loggable_rows
            from utils.time_log import log_time

            rows = get_loggable_rows(date.today())
            row_idx = (y - INTERVIEW_PREP_HEADER_Y) // INTERVIEW_PREP_ROW_H
            if 0 <= row_idx < len(rows):
                row_y = INTERVIEW_PREP_HEADER_Y + row_idx * INTERVIEW_PREP_ROW_H
                btn_y = row_y + (INTERVIEW_PREP_ROW_H - LOG_BTN_H) // 2
                if btn_y <= y <= btn_y + LOG_BTN_H:
                    (x0_15, x1_15), (x0_30, x1_30) = get_log_button_ranges(Config.DASHBOARD_WIDTH)
                    row = rows[row_idx]
                    minutes = None
                    if x0_15 <= x <= x1_15:
                        minutes = 15
                    elif x0_30 <= x <= x1_30:
                        minutes = 30
                    if minutes:
                        log_time(row["category"], minutes, item_id=row["item_id"])
                        _safe_refresh()
                        return f"Tap ({x},{y}) -> log +{minutes}m on {row['label']}"
        return f"Tap ({x},{y}) -> interview_prep tap -- ignored"

    # ── Weekly detail view (running only): back goes to dashboard, row tap opens day detail ─
    if view == "running":
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            set_view("dashboard")
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> dashboard"
        if y >= WEEKLY_HEADER_Y:
            row_idx = (y - WEEKLY_HEADER_Y) // WEEKLY_ROW_H
            if 0 <= row_idx <= 6:
                today = date.today()
                monday = today - timedelta(days=today.weekday())
                selected = monday + timedelta(days=row_idx)
                set_view("running_day", selected.isoformat())
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
    interview_top = TOP_PADDING
    interview_bottom = TOP_PADDING + INTERVIEW_SECTION_HEIGHT
    running_top = interview_bottom
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

    if interview_top <= y < interview_bottom:
        set_view("interview_prep")
        _safe_refresh()
        return f"Tap ({x},{y}) -> INTERVIEW section -> interview prep detail view"

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
