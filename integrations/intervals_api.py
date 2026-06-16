"""Fetch and summarize recent training history from intervals.icu."""
from datetime import date, timedelta
from collections import defaultdict

import requests

from config import Config

_BASE = "https://intervals.icu/api/v1"
_WEEKS_OF_HISTORY = 12


def _auth():
    return ("API_KEY", Config.INTERVALS_API_KEY)


def _meters_to_miles(m: float) -> float:
    return round(m / 1609.344, 2)


def _seconds_to_mmss(secs: float) -> str:
    if not secs or secs <= 0:
        return "?"
    mins = int(secs) // 60
    s = int(secs) % 60
    return f"{mins}:{s:02d}"


def _pace_per_mile(distance_m: float, moving_time_s: float) -> str:
    """Returns pace as MM:SS/mi, or '?' if data unavailable."""
    if not distance_m or not moving_time_s or distance_m <= 0:
        return "?"
    secs_per_meter = moving_time_s / distance_m
    secs_per_mile = secs_per_meter * 1609.344
    return _seconds_to_mmss(secs_per_mile)


def fetch_recent_activities(weeks: int = _WEEKS_OF_HISTORY) -> list[dict]:
    """Fetch run activities from the last N weeks. Returns [] if unavailable."""
    if not Config.INTERVALS_API_KEY or not Config.INTERVALS_ATHLETE_ID:
        return []

    oldest = (date.today() - timedelta(weeks=weeks)).isoformat()
    newest = date.today().isoformat()

    try:
        r = requests.get(
            f"{_BASE}/athlete/{Config.INTERVALS_ATHLETE_ID}/activities",
            auth=_auth(),
            params={
                "oldest": oldest,
                "newest": newest,
                "fields": "name,start_date_local,type,distance,moving_time,average_speed,laps",
            },
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        return []

    activities = []
    for a in r.json():
        # Skip Strava-blocked activities or non-run types
        if a.get("_note") or a.get("type") not in ("Run", "TrailRun", "VirtualRun"):
            continue
        distance_m = a.get("distance") or 0
        moving_time_s = a.get("moving_time") or 0
        activities.append({
            "date": a.get("start_date_local", "")[:10],
            "name": a.get("name", ""),
            "type": a.get("type", "Run"),
            "distance_miles": _meters_to_miles(distance_m),
            "moving_time_s": moving_time_s,
            "pace_per_mile": _pace_per_mile(distance_m, moving_time_s),
            "laps": a.get("laps") or [],
        })

    return sorted(activities, key=lambda x: x["date"])


def summarize_training_history(activities: list[dict]) -> str:
    """Convert raw activity list into a human-readable training history block for Claude."""
    if not activities:
        return ""

    # Group by ISO week (Monday-based)
    by_week: dict[str, list] = defaultdict(list)
    for a in activities:
        try:
            d = date.fromisoformat(a["date"])
            monday = d - timedelta(days=d.weekday())
            by_week[monday.isoformat()].append(a)
        except ValueError:
            continue

    weeks_sorted = sorted(by_week.keys())
    total_weeks = len(weeks_sorted)

    lines = [f"RECENT TRAINING HISTORY ({total_weeks} weeks of data from intervals.icu):"]

    weekly_totals = []
    long_runs = []

    for monday_str in weeks_sorted:
        week_acts = by_week[monday_str]
        monday = date.fromisoformat(monday_str)
        sunday = monday + timedelta(days=6)
        total_miles = sum(a["distance_miles"] for a in week_acts)
        weekly_totals.append(total_miles)
        longest = max(week_acts, key=lambda x: x["distance_miles"]) if week_acts else None
        if longest:
            long_runs.append(longest["distance_miles"])

        runs_desc = []
        for a in sorted(week_acts, key=lambda x: x["date"]):
            runs_desc.append(
                f"{a['date']}: {a['distance_miles']} mi @ {a['pace_per_mile']}/mi"
                + (f" ({a['name']})" if a["name"] else "")
            )

        label = f"Week of {monday.strftime('%b %d')}–{sunday.strftime('%b %d')}"
        lines.append(f"\n  {label} — {round(total_miles, 1)} mi total ({len(week_acts)} runs)")
        for r in runs_desc:
            lines.append(f"    {r}")

    # Summary stats
    if weekly_totals:
        non_zero = [w for w in weekly_totals if w > 0]
        avg_weekly = round(sum(non_zero) / len(non_zero), 1) if non_zero else 0
        peak_weekly = round(max(weekly_totals), 1)
        avg_long = round(sum(long_runs) / len(long_runs), 1) if long_runs else 0
        peak_long = round(max(long_runs), 1) if long_runs else 0
        recent_4 = [w for w in weekly_totals[-4:] if w > 0]
        recent_avg = round(sum(recent_4) / len(recent_4), 1) if recent_4 else 0

        lines.insert(1, (
            f"\n  Summary: avg {avg_weekly} mi/week over {total_weeks} weeks "
            f"| recent 4-week avg: {recent_avg} mi "
            f"| peak week: {peak_weekly} mi "
            f"| avg long run: {avg_long} mi "
            f"| longest run: {peak_long} mi\n"
        ))

    return "\n".join(lines)


def get_training_context() -> str:
    """Top-level function: fetch + summarize. Returns '' if no data available."""
    activities = fetch_recent_activities()
    return summarize_training_history(activities)
