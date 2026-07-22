"""Render the dashboard (or a detail view) and push it to the Kindle. Run from project root."""
import sys
from datetime import date, datetime

from config import Config
from dashboard.push import push_to_kindle
from dashboard.render import (
    render_birthdays_detail,
    render_dashboard,
    render_learning_detail,
    render_running_day_detail,
    render_running_detail,
    save_dashboard,
)
from integrations.intervals_api import get_todays_run_detail, is_run_completed_today
from utils.learning import get_loggable_rows
from utils.kindle_state import get_pending_minutes, get_selected_date, get_view
from utils.leetcode_history import get_today as get_leetcode_today
from utils.plan import (
    get_todays_run_plan,
    get_upcoming_birthdays,
    get_week_run_plan,
    load_birthdays,
    load_plan,
)
from utils.run_feedback import get_or_generate_feedback
from utils.run_route import get_or_fetch_route


def _format_now(now: datetime) -> str:
    """e.g. 'Friday, May 22 at 8:42 PM' — cross-platform (no %-d / %-I)."""
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    return f"{date_part} at {time_part}"


def run(push: bool = True) -> None:
    today = date.today()
    view = get_view()

    # Refresh the local LeetCode-solved-today record on every invocation (rides
    # the existing 30-min dashboard-refresh scheduler job — no separate job needed).
    leetcode_today = get_leetcode_today(Config.LEETCODE_USERNAME)

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
        day_route = get_or_fetch_route(selected) if day_completed else []
        img = render_running_day_detail(run_day, selected, day_completed, route=day_route)

    elif view == "learning":
        rows = get_loggable_rows(today)
        img = render_learning_detail(rows, leetcode_today)

    elif view == "birthdays":
        img = render_birthdays_detail(load_birthdays(), today)

    else:
        last_refreshed_label = _format_now(datetime.now())
        learning_rows = get_loggable_rows(today)
        pending_minutes = get_pending_minutes()
        run_plan = get_todays_run_plan(today)
        run_completed = is_run_completed_today()
        birthdays = get_upcoming_birthdays(today, days_ahead=7)

        run_feedback = None
        run_route = []
        actual_run = None
        if run_completed and run_plan:
            week_plan = get_week_run_plan(today)
            active = (load_plan().get("running") or {}).get("active") or {}
            plan_meta = {
                "race_name": active.get("race_name", ""),
                "race_date": active.get("race_date", ""),
                "start_date": active.get("start_date", ""),
            }
            run_feedback = get_or_generate_feedback(today, run_plan, week_plan, plan_meta)
            run_route = get_or_fetch_route(today)
            actual_run = get_todays_run_detail()

        img = render_dashboard(
            learning_rows=learning_rows,
            pending_minutes=pending_minutes,
            leetcode_today=leetcode_today,
            run=run_plan,
            run_completed=run_completed,
            birthdays=birthdays,
            last_refreshed_label=last_refreshed_label,
            run_feedback=run_feedback,
            route=run_route,
            actual_run=actual_run,
        )

    image_path = save_dashboard(img)
    print(f"Dashboard saved to {image_path} (view={view})")

    if push:
        push_to_kindle(image_path)
        print("Pushed to Kindle.")


def push_only() -> None:
    """Push the already-rendered dashboard.png without re-rendering (used to push in the background)."""
    push_to_kindle(Config.OUTPUT_IMAGE_PATH)
    print("Pushed to Kindle.")


if __name__ == "__main__":
    if "--push-only" in sys.argv:
        push_only()
    else:
        run(push="--no-push" not in sys.argv)
