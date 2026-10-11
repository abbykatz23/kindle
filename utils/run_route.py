"""Cache run GPS routes (list of lat/lng points), keyed per calendar day, in data/run_route.json.

Only the MAX_CACHED_ROUTES most recently used entries are kept, so the file stays small."""
import json
from datetime import date
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "data" / "run_route.json"
MAX_CACHED_ROUTES = 10


def _load_cache() -> dict:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    # Dicts keep insertion order, and entries are moved to the end on use, so the
    # oldest-used entries are at the front.
    for key in list(cache)[:-MAX_CACHED_ROUTES]:
        del cache[key]
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache))


def _get_cached(cache: dict, key: str) -> list[tuple[float, float]] | None:
    """Return the cached route for key (marking it most recently used), or None on a miss."""
    if key not in cache:
        return None
    if list(cache)[-1] != key:
        cache[key] = cache.pop(key)
        _save_cache(cache)
    return [tuple(p) for p in cache[key]]


def get_or_fetch_route(on_date: date) -> list[tuple[float, float]]:
    """Return the cached GPS route for on_date, fetching from intervals.icu on first call.

    Returns [] (and caches that) if there's no run on that day or no GPS data for it,
    so treadmill/indoor days and repeated day-detail views don't re-hit the API.
    """
    cache = _load_cache()
    key = on_date.isoformat()
    cached = _get_cached(cache, key)
    if cached is not None:
        return cached

    from integrations.intervals_api import get_route_points, get_run_detail_for_date

    run = get_run_detail_for_date(on_date)
    points: list[tuple[float, float]] = []
    if run and run.get("id"):
        points = get_route_points(run["id"])

    cache[key] = points
    _save_cache(cache)
    return points


def get_or_fetch_route_for_activity(activity_id: str) -> list[tuple[float, float]]:
    """Like get_or_fetch_route, but keyed by a specific intervals.icu activity id
    (so a day with multiple runs still maps to the right one)."""
    cache = _load_cache()
    key = f"activity:{activity_id}"
    cached = _get_cached(cache, key)
    if cached is not None:
        return cached

    from integrations.intervals_api import get_route_points

    points = get_route_points(activity_id)
    cache[key] = points
    _save_cache(cache)
    return points
