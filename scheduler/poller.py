"""
Triggers a dashboard re-render + push to the Kindle.

Without args (cron flow): unconditional refresh — polls all APIs and pushes a new image.
With --tap-x/--tap-y: interprets a Kindle tap, optionally toggles a manual completion,
                     then unconditional refresh.
"""
import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from config import Config
from dashboard.render import (
    INTERVIEW_TASKS_Y, MAX_TASKS_PER_SIDE, TASK_LINE_HEIGHT,
)
from utils.completions import toggle_manual_completion
from utils.plan import get_todays_interview_tasks

_PROJECT_ROOT = Path(__file__).parent.parent


def _trigger_render_and_push() -> None:
    """Spawn main.py, which polls all APIs, renders, and pushes to the Kindle."""
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py")],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )


def _handle_tap(x: int, y: int) -> None:
    """Route a Kindle tap to the right action based on screen coordinates."""
    today = date.today()
    half_width = Config.DASHBOARD_WIDTH // 2

    if x >= half_width:
        # Right half: try to map y to a manual-completable task slot
        non_leetcode = [t for t in get_todays_interview_tasks(today)
                        if t.get("type") != "leetcode"][:MAX_TASKS_PER_SIDE]
        slot = (y - INTERVIEW_TASKS_Y) // TASK_LINE_HEIGHT
        if 0 <= slot < len(non_leetcode):
            task_name = non_leetcode[slot].get("task", "")
            new_state = toggle_manual_completion(today, task_name)
            print(f"Tap ({x},{y}) → right slot {slot}: '{task_name}' now "
                  f"{'done' if new_state else 'not done'}")
        else:
            print(f"Tap ({x},{y}) → right half but no task in slot {slot}: refresh only")
    else:
        print(f"Tap ({x},{y}) → left half: refresh (polls LeetCode + Strava)")

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
