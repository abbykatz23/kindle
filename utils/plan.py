"""Read/write helpers for plan.json, birthdays.json, and derived lookups."""
import calendar
import json
from datetime import date, timedelta

from config import Config


def load_plan() -> dict:
    if Config.PLAN_FILE.exists():
        return json.loads(Config.PLAN_FILE.read_text())
    return {"running": {}}


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


def get_todays_run_plan(today: date) -> dict | None:
    plan = load_plan()
    running = plan.get("running", {})
    active = running.get("active") if isinstance(running, dict) else None
    if not active:
        return None
    start_date = active.get("start_date")
    if not start_date:
        return None
    start = date.fromisoformat(start_date)
    start_monday = start - timedelta(days=start.weekday())
    today_monday = today - timedelta(days=today.weekday())
    week_num = max(1, ((today_monday - start_monday).days // 7) + 1)
    day_name = today.strftime("%A").lower()
    return active.get("weeks", {}).get(str(week_num), {}).get(day_name)


def update_run_plan_day(d: date, updates: dict) -> bool:
    """Merge `updates` into the active running plan's entry for date `d`.

    Returns False if there's no active plan covering this date.
    """
    plan = load_plan()
    running = plan.get("running", {})
    active = running.get("active") if isinstance(running, dict) else None
    if not active:
        return False
    start_date = active.get("start_date")
    if not start_date:
        return False
    start = date.fromisoformat(start_date)
    start_monday = start - timedelta(days=start.weekday())
    d_monday = d - timedelta(days=d.weekday())
    week_num = max(1, ((d_monday - start_monday).days // 7) + 1)
    day_name = d.strftime("%A").lower()

    weeks = active.setdefault("weeks", {})
    day_entry = weeks.setdefault(str(week_num), {}).setdefault(day_name, {})
    day_entry.update(updates)
    save_plan(plan)
    return True


def get_week_run_plan(today: date) -> dict:
    """Return {day_name: plan_dict} for the active plan's current week, or {} if no plan."""
    plan = load_plan()
    running = plan.get("running", {})
    active = running.get("active") if isinstance(running, dict) else None
    if not active:
        return {}
    start_date = active.get("start_date")
    if not start_date:
        return {}
    start = date.fromisoformat(start_date)
    start_monday = start - timedelta(days=start.weekday())
    today_monday = today - timedelta(days=today.weekday())
    week_num = max(1, ((today_monday - start_monday).days // 7) + 1)
    return active.get("weeks", {}).get(str(week_num), {})


def get_plan_week_bounds(today: date) -> tuple[int, int] | None:
    """Return (current_week_num, total_weeks) for the active plan, or None if there's no active plan.

    Shared by the Kindle weekly-view renderer and its tap handler so both agree on how
    far the PREV/NEXT week navigation is allowed to go.
    """
    plan = load_plan()
    running = plan.get("running", {})
    active = running.get("active") if isinstance(running, dict) else None
    if not active or not active.get("start_date"):
        return None
    start = date.fromisoformat(active["start_date"])
    start_monday = start - timedelta(days=start.weekday())
    today_monday = today - timedelta(days=today.weekday())
    current_week_num = max(1, ((today_monday - start_monday).days // 7) + 1)
    total_weeks = len(active.get("weeks", {}))
    return current_week_num, total_weeks


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
