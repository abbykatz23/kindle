"""Render the dashboard and push it to the Kindle. Run from project root."""
import sys
from datetime import date

from config import Config
from dashboard.push import push_to_kindle
from dashboard.render import render_dashboard, save_dashboard
from integrations.leetcode import is_problem_completed_today
from integrations.strava import is_run_completed_today
from utils.plan import get_todays_interview_task, get_todays_run_plan, get_upcoming_birthdays


def run(push: bool = True) -> None:
    today = date.today()
    today_label = f"{today.strftime('%A, %B')} {today.day}"

    run_plan = get_todays_run_plan(today)
    try:
        run_completed = is_run_completed_today()
    except Exception as e:
        print(f"Strava unavailable: {e}")
        run_completed = False

    interview = get_todays_interview_task(today)
    try:
        interview_completed = is_problem_completed_today(Config.LEETCODE_USERNAME)
    except Exception as e:
        print(f"LeetCode unavailable: {e}")
        interview_completed = False

    birthdays = get_upcoming_birthdays(today, days_ahead=2)

    img = render_dashboard(
        interview_task=interview,
        interview_completed=interview_completed,
        run=run_plan,
        run_completed=run_completed,
        birthdays=birthdays,
        today_label=today_label,
    )

    image_path = save_dashboard(img)
    print(f"Dashboard saved to {image_path}")

    if push:
        push_to_kindle(image_path)
        print("Pushed to Kindle.")


if __name__ == "__main__":
    run(push="--no-push" not in sys.argv)
