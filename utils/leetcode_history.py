"""Local daily record of LeetCode problems solved, derived from the LeetCode API.

The API only exposes recent submissions, not a queryable history, so we record our
own day-by-day snapshot each time `record_today` is called (e.g. on every dashboard
refresh) to let the frontend chart solve counts over time.
"""
import json
from datetime import date, datetime, timedelta

from config import Config
from integrations.leetcode import get_recent_accepted_submissions


def load_history() -> dict:
    if Config.LEETCODE_HISTORY_FILE.exists():
        try:
            return json.loads(Config.LEETCODE_HISTORY_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_history(history: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.LEETCODE_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def record_today(username: str) -> dict | None:
    """Fetch today's accepted submissions and overwrite today's history entry.

    Idempotent — the LeetCode API always reports the full set of today's accepted
    submissions, never a delta, so calling this repeatedly is safe. Returns None
    (without touching the file) if there's no username configured or the API call
    fails, so a transient outage never wipes already-recorded data.
    """
    if not username:
        return None
    try:
        submissions = get_recent_accepted_submissions(username, limit=100)
    except Exception:
        return None

    today_iso = date.today().isoformat()
    seen_slugs: set[str] = set()
    problems = []
    for sub in submissions:
        sub_date = date.fromtimestamp(int(sub["timestamp"])).isoformat()
        if sub_date != today_iso:
            continue
        slug = sub.get("titleSlug")
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        problems.append({"title": sub.get("title", ""), "titleSlug": slug})

    entry = {
        "count": len(problems),
        "problems": problems,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    history = load_history()
    history[today_iso] = entry
    save_history(history)
    return entry


def get_today(username: str) -> dict:
    """Return today's leetcode record, always refreshing from the API first."""
    recorded = record_today(username)
    if recorded is not None:
        return {"date": date.today().isoformat(), **recorded}
    stored = load_history().get(date.today().isoformat())
    if stored:
        return {"date": date.today().isoformat(), **stored}
    return {"date": date.today().isoformat(), "count": 0, "problems": []}


def get_history(start: date, end: date) -> dict[str, dict]:
    """Return {iso_date: {count, problems}} for every day in [start, end]."""
    history = load_history()
    out = {}
    d = start
    while d <= end:
        iso = d.isoformat()
        entry = history.get(iso, {})
        out[iso] = {"count": entry.get("count", 0), "problems": entry.get("problems", [])}
        d += timedelta(days=1)
    return out
