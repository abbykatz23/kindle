"""Cache run GPS routes (list of lat/lng points), keyed per calendar day, in data/run_route.json."""
import json
from datetime import date
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "data" / "run_route.json"


def _load_cache() -> dict:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache))


def get_or_fetch_route(on_date: date) -> list[tuple[float, float]]:
    """Return the cached GPS route for on_date, fetching from intervals.icu on first call.

    Returns [] (and caches that) if there's no run on that day or no GPS data for it,
    so treadmill/indoor days and repeated day-detail views don't re-hit the API.
    """
    cache = _load_cache()
    key = on_date.isoformat()
    if key in cache:
        return [tuple(p) for p in cache[key]]

    from integrations.intervals_api import get_route_points, get_run_detail_for_date

    run = get_run_detail_for_date(on_date)
    points: list[tuple[float, float]] = []
    if run and run.get("id"):
        points = get_route_points(run["id"])

    cache[key] = points
    _save_cache(cache)
    return points
