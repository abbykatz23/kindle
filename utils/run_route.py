"""Cache today's run GPS route (list of lat/lng points) in data/run_route.json."""
import json
from datetime import date
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "data" / "run_route.json"


def load_todays_route(today: date) -> list[tuple[float, float]] | None:
    """Return cached route for today (possibly []), or None if not yet cached."""
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text())
        if data.get("date") == today.isoformat():
            return [tuple(p) for p in data.get("points") or []]
    except Exception:
        pass
    return None


def save_route(today: date, points: list[tuple[float, float]]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps({"date": today.isoformat(), "points": points}))


def get_or_fetch_route(today: date) -> list[tuple[float, float]]:
    """Return today's cached GPS route, fetching from intervals.icu on first call.

    Returns [] (and caches that) if there's no run today or no GPS data for it,
    so treadmill/indoor days don't re-hit the API on every dashboard refresh.
    """
    cached = load_todays_route(today)
    if cached is not None:
        return cached

    from integrations.intervals_api import get_route_points, get_todays_run_detail

    run = get_todays_run_detail()
    points: list[tuple[float, float]] = []
    if run and run.get("id"):
        points = get_route_points(run["id"])

    save_route(today, points)
    return points
