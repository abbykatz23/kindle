"""
Runs every Sunday via cron.
Reads the monthly prep skeleton, calls Claude to generate next week's
interview prep tasks, and appends them to plan.json.
"""
from datetime import date, timedelta
from pathlib import Path

from integrations.claude_api import generate_weekly_interview_prep
from utils.plan import get_week_label, load_plan, save_plan

_SKELETON_FILE = Path(__file__).parent.parent / "data" / "monthly_skeleton.md"


def _next_week_label() -> str:
    today = date.today()
    next_monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    return get_week_label(next_monday)


def generate_and_save() -> None:
    skeleton = _SKELETON_FILE.read_text()
    plan = load_plan()
    prep = plan.setdefault("interview_prep", {})

    week_label = _next_week_label()
    if week_label in prep:
        print(f"{week_label} already exists — skipping.")
        return

    existing_weeks = sorted(prep.keys())
    tasks = generate_weekly_interview_prep(week_label, skeleton, existing_weeks)
    prep[week_label] = tasks
    save_plan(plan)
    print(f"Generated interview prep for {week_label}.")


if __name__ == "__main__":
    generate_and_save()
