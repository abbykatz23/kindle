"""Render the dashboard and push it to the Kindle. Run from project root."""
import sys
from datetime import date, datetime

from config import Config
from dashboard.push import push_to_kindle
from dashboard.render import render_dashboard, save_dashboard
from integrations.leetcode import is_problem_completed_today
from integrations.strava import is_run_completed_today
from utils.completions import get_manual_completions
from utils.plan import get_todays_interview_tasks, get_todays_run_plan, get_upcoming_birthdays


def _resolve_interview_tasks(today: date) -> list[dict]:
    """Attach a `completed` boolean to each of today's interview tasks."""
    tasks = get_todays_interview_tasks(today)
    manual = get_manual_completions(today)

    resolved = []
    for task in tasks:
        t = dict(task)
        if t.get("type") == "leetcode" and t.get("leetcode_slug"):
            try:
                t["completed"] = is_problem_completed_today(
                    Config.LEETCODE_USERNAME, t["leetcode_slug"]
                )
            except Exception as e:
                print(f"LeetCode unavailable for {t['leetcode_slug']}: {e}")
                t["completed"] = False
        else:
            t["completed"] = t.get("task", "") in manual
        resolved.append(t)
    return resolved


def _format_now(now: datetime) -> str:
    """e.g. 'Friday, May 22 at 8:42 PM' — cross-platform (no %-d / %-I)."""
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    return f"{date_part} at {time_part}"


def run(push: bool = True) -> None:
    today = date.today()
    last_refreshed_label = _format_now(datetime.now())

    interview_tasks = _resolve_interview_tasks(today)

    run_plan = get_todays_run_plan(today)
    try:
        run_completed = is_run_completed_today()
    except Exception as e:
        print(f"Strava unavailable: {e}")
        run_completed = False

    birthdays = get_upcoming_birthdays(today, days_ahead=7)

    img = render_dashboard(
        interview_tasks=interview_tasks,
        run=run_plan,
        run_completed=run_completed,
        birthdays=birthdays,
        last_refreshed_label=last_refreshed_label,
    )

    image_path = save_dashboard(img)
    print(f"Dashboard saved to {image_path}")

    if push:
        push_to_kindle(image_path)
        print("Pushed to Kindle.")


if __name__ == "__main__":
    run(push="--no-push" not in sys.argv)
