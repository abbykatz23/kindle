"""Append-only time-log for learning/project categories. Additive by construction."""
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from config import Config
from utils.learning_items import ITEM_CATEGORIES

FIXED_CATEGORIES = ("system_design",)
ALL_CATEGORIES = ITEM_CATEGORIES + FIXED_CATEGORIES
VALID_MINUTES = (5, 15, 30)


def load_log() -> list[dict]:
    if Config.LEARNING_TIME_LOG_FILE.exists():
        try:
            return json.loads(Config.LEARNING_TIME_LOG_FILE.read_text())
        except Exception:
            return []
    return []


def save_log(entries: list[dict]) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.LEARNING_TIME_LOG_FILE.write_text(json.dumps(entries, indent=2))


def _resolve_item_id(category: str, item_id: str | None) -> str | None:
    if category not in ALL_CATEGORIES:
        raise ValueError(f"Unknown category: {category!r}")
    if category in FIXED_CATEGORIES:
        return None
    if not item_id:
        raise ValueError(f"item_id is required for category {category!r}")
    return item_id


def _append_entry(category: str, minutes: int, item_id: str | None, on_date: date) -> dict:
    entry = {
        "id": uuid.uuid4().hex[:8],
        "date": on_date.isoformat(),
        "category": category,
        "item_id": item_id,
        "minutes": minutes,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
    }
    entries = load_log()
    entries.append(entry)
    save_log(entries)
    return entry


def log_time(category: str, minutes: int, item_id: str | None = None, on_date: date | None = None) -> dict:
    """Log time via the Kindle tap flow / dashboard quick-log buttons — fixed +5/+15/+30 increments only."""
    if minutes not in VALID_MINUTES:
        raise ValueError(f"minutes must be one of {VALID_MINUTES}")
    item_id = _resolve_item_id(category, item_id)
    return _append_entry(category, minutes, item_id, on_date or date.today())


def log_time_manual(category: str, minutes: int, item_id: str | None, on_date: date) -> dict:
    """Log an arbitrary amount of time against any date — web UI only, for backfilling missed entries."""
    if minutes <= 0:
        raise ValueError("minutes must be a positive number")
    item_id = _resolve_item_id(category, item_id)
    return _append_entry(category, minutes, item_id, on_date)


def get_totals_for_date(on_date: date) -> dict[tuple[str, str | None], int]:
    """Single-pass sum of minutes for every (category, item_id) on the given date."""
    iso = on_date.isoformat()
    totals: dict[tuple[str, str | None], int] = defaultdict(int)
    for entry in load_log():
        if entry.get("date") == iso:
            key = (entry.get("category"), entry.get("item_id"))
            totals[key] += entry.get("minutes", 0)
    return dict(totals)


def get_total_minutes(category: str, item_id: str | None, on_date: date) -> int:
    return get_totals_for_date(on_date).get((category, item_id), 0)


def get_category_totals_by_day(start: date, end: date) -> dict[str, dict[str, int]]:
    """Return {iso_date: {category: minutes}} for every day in [start, end]."""
    by_day: dict[str, dict[str, int]] = {}
    d = start
    while d <= end:
        by_day[d.isoformat()] = {}
        d += timedelta(days=1)

    for entry in load_log():
        iso = entry.get("date")
        if iso in by_day:
            category = entry.get("category")
            by_day[iso][category] = by_day[iso].get(category, 0) + entry.get("minutes", 0)

    return by_day


def get_item_history(item_id: str, start: date, end: date) -> dict[str, int]:
    """Return {iso_date: minutes} for a single item over [start, end]."""
    history = {}
    d = start
    while d <= end:
        history[d.isoformat()] = 0
        d += timedelta(days=1)

    for entry in load_log():
        iso = entry.get("date")
        if iso in history and entry.get("item_id") == item_id:
            history[iso] += entry.get("minutes", 0)

    return history
