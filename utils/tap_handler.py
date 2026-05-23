"""Shared tap routing logic — used by both the Flask /tap endpoint and scheduler/poller.py."""
import subprocess
import sys
from datetime import date
from pathlib import Path

from config import Config
from dashboard.render import (
    INTERVIEW_SECTION_HEIGHT, INTERVIEW_TASKS_Y, MAX_TASKS_PER_SIDE,
    TASK_LINE_HEIGHT, TOP_PADDING,
)
from utils.completions import toggle_manual_completion
from utils.plan import get_week_task_lists

_PROJECT_ROOT = Path(__file__).parent.parent


def trigger_refresh() -> None:
    """Re-render the dashboard and push it to the Kindle (blocking)."""
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py")],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )


def handle_tap(x: int, y: int) -> str:
    """Process a Kindle tap and return a human-readable result string."""
    half_width = Config.DASHBOARD_WIDTH // 2
    interview_top = TOP_PADDING
    interview_bottom = TOP_PADDING + INTERVIEW_SECTION_HEIGHT

    if not (interview_top <= y < interview_bottom):
        return f"Tap ({x},{y}) -> outside interview section -- ignored"

    if x < half_width:
        _safe_refresh()
        return f"Tap ({x},{y}) -> LEETCODE column -- refresh"

    slot = (y - INTERVIEW_TASKS_Y) // TASK_LINE_HEIGHT
    if slot < 0 or slot >= MAX_TASKS_PER_SIDE:
        return f"Tap ({x},{y}) -> OTHER column but not on a task slot -- ignored"

    _, other_tasks = get_week_task_lists(date.today())
    if slot >= len(other_tasks):
        return f"Tap ({x},{y}) -> OTHER slot {slot} is empty -- ignored"

    task = other_tasks[slot]
    task_date = date.fromisoformat(task["date"])
    new_state = toggle_manual_completion(task_date, task["task"])
    _safe_refresh()
    return (f"Tap ({x},{y}) -> toggled '{task['task']}' ({task['date']}) -> "
            f"{'done' if new_state else 'not done'}")


def _safe_refresh() -> None:
    """Refresh without surfacing render/push errors to the caller (so /tap doesn't 500)."""
    try:
        trigger_refresh()
    except Exception as e:
        print(f"refresh failed: {e}", file=sys.stderr)
