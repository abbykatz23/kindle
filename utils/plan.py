"""Read/write helpers for plan.json, birthdays.json, and derived lookups."""
import json
from datetime import date

from config import Config


def load_plan() -> dict:
    if Config.PLAN_FILE.exists():
        return json.loads(Config.PLAN_FILE.read_text())
    return {"running": {}, "interview_prep": {}}


def save_plan(plan: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.PLAN_FILE.write_text(json.dumps(plan, indent=2))


def load_birthdays() -> list[dict]:
    if Config.BIRTHDAYS_FILE.exists():
        return json.loads(Config.BIRTHDAYS_FILE.read_text())
    return []


def get_week_label(d: date) -> str:
    """ISO week string, e.g. '2026-W19'."""
    return d.strftime("%G-W%V")


def get_week_monday(week_label: str) -> date:
    year, week = week_label.split("-W")
    return date.fromisocalendar(int(year), int(week), 1)


def get_todays_run_plan(today: date) -> dict | None:
    plan = load_plan()
    day_name = today.strftime("%A").lower()
    return plan.get("running", {}).get(get_week_label(today), {}).get(day_name)


def get_todays_interview_tasks(today: date) -> list[dict]:
    """Return today's interview prep tasks as a list (may be empty).

    Each task has at minimum a `type` and `task` field. LeetCode tasks also have
    `leetcode_slug`. Non-LeetCode tasks may have `notes`.
    """
    plan = load_plan()
    day_name = today.strftime("%A").lower()
    raw = plan.get("interview_prep", {}).get(get_week_label(today), {}).get(day_name, [])
    return raw if isinstance(raw, list) else []


def get_upcoming_birthdays(today: date, days_ahead: int = 2) -> list[dict]:
    upcoming = []
    for entry in load_birthdays():
        month, day = map(int, entry["date"].split("-"))
        try:
            birthday = date(today.year, month, day)
        except ValueError:
            continue  # Feb 29 on non-leap year
        delta = (birthday - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append({
                **entry,
                "days_until": delta,
                "formatted_date": f"{birthday.strftime('%B')} {_ordinal(birthday.day)}",
            })
    return upcoming


def _ordinal(n: int) -> str:
    """Day-of-month with English ordinal suffix: 1 → 1st, 22 → 22nd, 11 → 11th."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")
