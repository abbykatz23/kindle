"""Render the dashboard and push it to the Kindle. Run from project root."""
import sys
from datetime import date, datetime, timedelta

from config import Config
from dashboard.push import push_to_kindle
from dashboard.render import render_dashboard, save_dashboard
from integrations.leetcode import get_recent_accepted_submissions
from integrations.strava import is_run_completed_today
from utils.completions import get_manual_completions
from utils.plan import get_tasks_for_date, get_todays_run_plan, get_upcoming_birthdays


def _format_now(now: datetime) -> str:
    """e.g. 'Friday, May 22 at 8:42 PM' — cross-platform (no %-d / %-I)."""
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    return f"{date_part} at {time_part}"


def _fetch_leetcode_completions_for_week(monday: date) -> set[tuple[str, str]]:
    """Return {(titleSlug, isoDate)} for every accepted submission this week."""
    if not Config.LEETCODE_USERNAME:
        return set()
    try:
        submissions = get_recent_accepted_submissions(Config.LEETCODE_USERNAME, limit=100)
    except Exception as e:
        print(f"LeetCode unavailable: {e}")
        return set()
    week_dates = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
    out = set()
    for sub in submissions:
        sub_date = date.fromtimestamp(int(sub["timestamp"])).isoformat()
        if sub_date in week_dates:
            out.add((sub["titleSlug"], sub_date))
    return out


def _build_week_task_lists(today: date) -> tuple[list[dict], list[dict]]:
    """Return (leetcode_tasks, other_tasks) flattened across the whole week."""
    monday = today - timedelta(days=today.weekday())
    leetcode_done = _fetch_leetcode_completions_for_week(monday)

    leetcode_tasks: list[dict] = []
    other_tasks: list[dict] = []
    for i in range(7):
        day = monday + timedelta(days=i)
        iso = day.isoformat()
        manual_done = get_manual_completions(day)

        for task in get_tasks_for_date(day):
            t = dict(task)
            if t.get("type") == "leetcode" and t.get("leetcode_slug"):
                t["completed"] = (t["leetcode_slug"], iso) in leetcode_done
                leetcode_tasks.append(t)
            else:
                t["completed"] = t.get("task", "") in manual_done
                other_tasks.append(t)
    return leetcode_tasks, other_tasks


def run(push: bool = True) -> None:
    today = date.today()
    last_refreshed_label = _format_now(datetime.now())

    leetcode_tasks, other_tasks = _build_week_task_lists(today)

    run_plan = get_todays_run_plan(today)
    try:
        run_completed = is_run_completed_today()
    except Exception as e:
        print(f"Strava unavailable: {e}")
        run_completed = False

    birthdays = get_upcoming_birthdays(today, days_ahead=7)

    img = render_dashboard(
        leetcode_tasks=leetcode_tasks,
        other_tasks=other_tasks,
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
