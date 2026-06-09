"""Read/write helpers for plan.json, birthdays.json, and derived lookups."""
import calendar
import json
from datetime import date, timedelta

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


def save_birthdays(birthdays: list[dict]) -> None:
    """Persist the birthdays list to disk (overwrites file)."""
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.BIRTHDAYS_FILE.write_text(json.dumps(birthdays, indent=2))


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


def get_tasks_for_date(d: date) -> list[dict]:
    """Return interview prep tasks for the given date (may be empty list)."""
    plan = load_plan()
    day_name = d.strftime("%A").lower()
    raw = plan.get("interview_prep", {}).get(get_week_label(d), {}).get(day_name, [])
    return raw if isinstance(raw, list) else []


def get_todays_interview_tasks(today: date) -> list[dict]:
    """Backward-compatible alias used by the tap handler."""
    return get_tasks_for_date(today)


def get_week_task_lists(today: date) -> tuple[list[dict], list[dict]]:
    """Return (leetcode_tasks, other_tasks) for the current ISO week.

    Tasks are returned in chronological order (Monday → Sunday). Each task dict
    is annotated with a `date` field (ISO date string) so callers can map a
    list position back to the underlying day. Completion status is NOT computed
    here — that's the caller's responsibility.
    """
    monday = today - timedelta(days=today.weekday())
    leetcode_tasks: list[dict] = []
    other_tasks: list[dict] = []
    for i in range(7):
        day = monday + timedelta(days=i)
        iso = day.isoformat()
        for task in get_tasks_for_date(day):
            t = dict(task)
            t["date"] = iso
            if t.get("type") == "leetcode":
                leetcode_tasks.append(t)
            else:
                other_tasks.append(t)
    return leetcode_tasks, other_tasks


def get_upcoming_birthdays(today: date, days_ahead: int = 7) -> list[dict]:
    upcoming = []
    for entry in load_birthdays():
        month, day = map(int, entry["date"].split("-"))
        if month == 2 and day == 29 and not calendar.isleap(today.year):
            birthday = date(today.year, 3, 1)
        else:
            try:
                birthday = date(today.year, month, day)
            except ValueError:
                continue
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
