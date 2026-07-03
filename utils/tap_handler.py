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
    INTERVIEW_SECTION_HEIGHT,
    RUNNING_SECTION_HEIGHT,
    TOP_PADDING,
    WEEKLY_HEADER_Y,
    WEEKLY_ROW_H,
)
from utils.kindle_state import get_view, set_view

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

    # ── Day detail views: only the back button is interactive ─────────────────
    if view in ("running_day", "interview_day"):
        if x <= BACK_BUTTON_MAX_X and y <= BACK_BUTTON_MAX_Y:
            parent = "running" if view == "running_day" else "interview"
            set_view(parent)
            _safe_refresh()
            return f"Tap ({x},{y}) -> BACK -> {parent}"
        return f"Tap ({x},{y}) -> {view} tap -- ignored"

    # ── Weekly detail views: back goes to dashboard, row tap opens day detail ─
    if view in ("running", "interview"):
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
                day_view = "running_day" if view == "running" else "interview_day"
                set_view(day_view, selected.isoformat())
                _safe_refresh()
                return f"Tap ({x},{y}) -> {view} day {selected.isoformat()}"
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
        set_view("interview")
        _safe_refresh()
        return f"Tap ({x},{y}) -> INTERVIEW section -> interview detail view"

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
