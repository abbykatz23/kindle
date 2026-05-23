"""
Triggers a dashboard re-render + push to the Kindle.

Without args (cron flow): polls APIs, re-renders, pushes.
With --tap-x/--tap-y: routes a Kindle tap based on screen coordinates.

Tap regions:
  - LEETCODE column (left half of interview section) -- any tap -> refresh
  - OTHER column (right half of interview section) -- only taps on a real
    task slot toggle that task's manual completion; taps elsewhere in the
    column do nothing
  - Everything else (running, birthdays, footer, padding) -- do nothing
"""
import argparse
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


def _trigger_render_and_push() -> None:
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py")],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )


def _handle_tap(x: int, y: int) -> None:
    """Route a Kindle tap to the right action based on screen coordinates."""
    half_width = Config.DASHBOARD_WIDTH // 2
    interview_top = TOP_PADDING
    interview_bottom = TOP_PADDING + INTERVIEW_SECTION_HEIGHT

    if not (interview_top <= y < interview_bottom):
        print(f"Tap ({x},{y}) -> outside interview section -- ignored")
        return

    if x < half_width:
        print(f"Tap ({x},{y}) -> LEETCODE column -- refresh")
        _trigger_render_and_push()
        return

    # OTHER column -- toggle the task at the tapped slot, if any
    slot = (y - INTERVIEW_TASKS_Y) // TASK_LINE_HEIGHT
    if slot < 0 or slot >= MAX_TASKS_PER_SIDE:
        print(f"Tap ({x},{y}) -> OTHER column but not on a task slot -- ignored")
        return

    _, other_tasks = get_week_task_lists(date.today())
    if slot >= len(other_tasks):
        print(f"Tap ({x},{y}) -> OTHER slot {slot} is empty -- ignored")
        return

    task = other_tasks[slot]
    task_date = date.fromisoformat(task["date"])
    new_state = toggle_manual_completion(task_date, task["task"])
    print(f"Tap ({x},{y}) -> toggled '{task['task']}' ({task['date']}) -> "
          f"{'done' if new_state else 'not done'}")
    _trigger_render_and_push()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tap-x", type=int, help="X coordinate of a Kindle tap")
    parser.add_argument("--tap-y", type=int, help="Y coordinate of a Kindle tap")
    args = parser.parse_args()

    if args.tap_x is not None and args.tap_y is not None:
        _handle_tap(args.tap_x, args.tap_y)
    else:
        _trigger_render_and_push()


if __name__ == "__main__":
    main()
