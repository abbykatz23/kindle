"""Render the dashboard (or a detail view) and push it to the Kindle. Run from project root."""
import sys
from datetime import date, datetime, timedelta

from config import Config
from dashboard.push import push_to_kindle
from dashboard.render import (
    render_birthdays_detail,
    render_dashboard,
    render_interview_day_detail,
    render_interview_detail,
    render_running_day_detail,
    render_running_detail,
    save_dashboard,
)
from integrations.intervals_api import is_run_completed_today
from integrations.leetcode import get_recent_accepted_submissions
from utils.completions import get_manual_completions
from utils.kindle_state import get_selected_date, get_view
from utils.plan import (
    get_tasks_for_date,
    get_todays_run_plan,
    get_upcoming_birthdays,
    get_week_run_plan,
    get_week_task_lists,
    load_birthdays,
    load_plan,
)
from utils.run_feedback import get_or_generate_feedback


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


def _attach_completion(today: date) -> tuple[list[dict], list[dict]]:
    """Same as get_week_task_lists, but with a `completed` field on each task."""
    monday = today - timedelta(days=today.weekday())
    leetcode_done = _fetch_leetcode_completions_for_week(monday)
    leetcode_tasks, other_tasks = get_week_task_lists(today)

    for t in leetcode_tasks:
        if t.get("leetcode_slug"):
            t["completed"] = (t["leetcode_slug"], t["date"]) in leetcode_done
        else:
            t["completed"] = False

    for t in other_tasks:
        manual_done = get_manual_completions(date.fromisoformat(t["date"]))
        t["completed"] = t.get("task", "") in manual_done

    return leetcode_tasks, other_tasks


def run(push: bool = True) -> None:
    today = date.today()
    view = get_view()

    if view == "running":
        week_plan = get_week_run_plan(today)
        run_completed = is_run_completed_today()
        img = render_running_detail(week_plan, today, run_completed)

    elif view == "running_day":
        selected_iso = get_selected_date()
        selected = date.fromisoformat(selected_iso) if selected_iso else today
        week_plan = get_week_run_plan(today)
        day_name = selected.strftime("%A").lower()
        run_day = week_plan.get(day_name)
        day_completed = is_run_completed_today() if selected == today else False
        img = render_running_day_detail(run_day, selected, day_completed)

    elif view == "interview":
        leetcode_tasks, other_tasks = _attach_completion(today)
        img = render_interview_detail(leetcode_tasks + other_tasks, today)

    elif view == "interview_day":
        selected_iso = get_selected_date()
        selected = date.fromisoformat(selected_iso) if selected_iso else today
        monday = today - timedelta(days=today.weekday())
        if monday <= selected < monday + timedelta(days=7):
            leetcode_tasks, other_tasks = _attach_completion(today)
            all_tasks = leetcode_tasks + other_tasks
            day_tasks = [t for t in all_tasks if t.get("date") == selected.isoformat()]
        else:
            day_tasks = [dict(t, completed=False) for t in get_tasks_for_date(selected)]
        img = render_interview_day_detail(day_tasks, selected)

    elif view == "birthdays":
        img = render_birthdays_detail(load_birthdays(), today)

    else:
        last_refreshed_label = _format_now(datetime.now())
        leetcode_tasks, other_tasks = _attach_completion(today)
        interview_tasks = leetcode_tasks + other_tasks
        run_plan = get_todays_run_plan(today)
        run_completed = is_run_completed_today()
        birthdays = get_upcoming_birthdays(today, days_ahead=7)

        run_feedback = None
        if run_completed and run_plan:
            week_plan = get_week_run_plan(today)
            active = (load_plan().get("running") or {}).get("active") or {}
            plan_meta = {
                "race_name": active.get("race_name", ""),
                "race_date": active.get("race_date", ""),
            }
            run_feedback = get_or_generate_feedback(today, run_plan, week_plan, plan_meta)

        img = render_dashboard(
            interview_tasks=interview_tasks,
            run=run_plan,
            run_completed=run_completed,
            birthdays=birthdays,
            last_refreshed_label=last_refreshed_label,
            run_feedback=run_feedback,
        )

    image_path = save_dashboard(img)
    print(f"Dashboard saved to {image_path} (view={view})")

    if push:
        push_to_kindle(image_path)
        print("Pushed to Kindle.")


if __name__ == "__main__":
    run(push="--no-push" not in sys.argv)
