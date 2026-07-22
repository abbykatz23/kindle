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


def get_run_detail_for_date(on_date: date) -> dict | None:
    """Return the first run activity logged on the given date, with distance/pace/splits, or None."""
    if not Config.INTERVALS_API_KEY or not Config.INTERVALS_ATHLETE_ID:
        return None
    date_str = on_date.isoformat()
    try:
        r = requests.get(
            f"{_BASE}/athlete/{Config.INTERVALS_ATHLETE_ID}/activities",
            auth=_auth(),
            params={
                "oldest": date_str,
                "newest": date_str,
                "fields": "id,name,start_date_local,type,distance,moving_time,average_speed,laps",
            },
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        return None
    for a in r.json():
        if a.get("_note") or a.get("type") not in ("Run", "TrailRun", "VirtualRun"):
            continue
        distance_m = a.get("distance") or 0
        moving_time_s = a.get("moving_time") or 0
        return {
            "id": a.get("id"),
            "name": a.get("name", ""),
            "distance_miles": _meters_to_miles(distance_m),
            "moving_time_s": moving_time_s,
            "pace_per_mile": _pace_per_mile(distance_m, moving_time_s),
            "laps": a.get("laps") or [],
        }
    return None


def get_todays_run_detail() -> dict | None:
    """Return the first run activity logged today, with distance/pace/splits, or None."""
    return get_run_detail_for_date(date.today())


def get_route_points(activity_id: str) -> list[tuple[float, float]]:
    """Return [(lat, lng), ...] GPS points for an activity, or [] if unavailable.

    intervals.icu's "latlng" stream stores latitude in `data` and longitude in
    a separate `data2` field on the same stream object (not documented clearly —
    the two are NOT interleaved in a single array).
    """
    if not Config.INTERVALS_API_KEY or not activity_id:
        return []
    try:
        r = requests.get(
            f"{_BASE}/activity/{activity_id}/streams",
            auth=_auth(),
            params={"types": "latlng"},
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        return []
    for s in r.json():
        if s.get("type") == "latlng":
            lats = s.get("data") or []
            lngs = s.get("data2") or []
            return [(lat, lng) for lat, lng in zip(lats, lngs) if lat is not None and lng is not None]
    return []


def is_run_completed_today() -> bool:
    """Return True if a run activity was logged today in intervals.icu."""
    if not Config.INTERVALS_API_KEY or not Config.INTERVALS_ATHLETE_ID:
        return False
    today_str = date.today().isoformat()
    try:
        r = requests.get(
            f"{_BASE}/athlete/{Config.INTERVALS_ATHLETE_ID}/activities",
            auth=_auth(),
            params={"oldest": today_str, "newest": today_str, "fields": "type,start_date_local"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        return False
    return any(
        a.get("type") in ("Run", "TrailRun", "VirtualRun")
        for a in r.json()
        if not a.get("_note")
    )


def get_training_context() -> str:
    """Top-level function: fetch + summarize. Returns '' if no data available."""
    activities = fetch_recent_activities()
    return summarize_training_history(activities)


# ── Week compliance ───────────────────────────────────────────────────────────

_COMPLIANCE_THRESHOLD_MILES = 0.55
_PLAN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def analyze_week_compliance(week_plan: dict, week_monday: date, plan_start_date: str = "") -> dict:
    """Compare assigned plan vs actual intervals.icu activities for past days of the week.

    Returns:
        has_data: False if no native activity data is available at all
        planned_miles: total assigned miles for evaluated (past) days
        actual_miles: total actual miles logged for those days
        missed_runs: list of {day, planned, date} where run was fully skipped
        short_runs: list of {day, planned, actual, date} where gap > threshold
        summary_text: human-readable string for Claude prompt (empty if compliant)
    """
    empty = {
        "has_data": False,
        "planned_miles": 0.0,
        "actual_miles": 0.0,
        "missed_runs": [],
        "short_runs": [],
        "summary_text": "",
    }
    if not Config.INTERVALS_API_KEY or not Config.INTERVALS_ATHLETE_ID:
        return empty

    today = date.today()
    week_sunday = week_monday + timedelta(days=6)
    fetch_until = min(today, week_sunday)

    try:
        r = requests.get(
            f"{_BASE}/athlete/{Config.INTERVALS_ATHLETE_ID}/activities",
            auth=_auth(),
            params={
                "oldest": week_monday.isoformat(),
                "newest": fetch_until.isoformat(),
                "fields": "start_date_local,type,distance",
            },
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        return empty

    actuals: dict[str, float] = defaultdict(float)
    for a in r.json():
        if a.get("_note") or a.get("type") not in ("Run", "TrailRun", "VirtualRun"):
            continue
        day_str = a.get("start_date_local", "")[:10]
        actuals[day_str] += _meters_to_miles(a.get("distance") or 0)

    if not actuals:
        return empty

    missed_runs = []
    short_runs = []
    planned_total = 0.0
    actual_total = 0.0

    plan_start_dt = date.fromisoformat(plan_start_date) if plan_start_date else week_monday

    for i, day_name in enumerate(_PLAN_DAYS):
        day_date = week_monday + timedelta(days=i)
        if day_date >= today or day_date < plan_start_dt:
            continue
        day_plan = week_plan.get(day_name, {})
        planned_type = day_plan.get("type", "rest")
        planned_miles = float(day_plan.get("distance_miles") or 0)
        if planned_type == "rest" or planned_miles == 0:
            continue
        actual_miles = actuals.get(day_date.isoformat(), 0.0)
        planned_total += planned_miles
        actual_total += actual_miles
        gap = planned_miles - actual_miles
        if actual_miles == 0:
            missed_runs.append({"day": day_name, "planned": planned_miles, "date": day_date.isoformat()})
        elif gap > _COMPLIANCE_THRESHOLD_MILES:
            short_runs.append({
                "day": day_name,
                "planned": planned_miles,
                "actual": round(actual_miles, 2),
                "date": day_date.isoformat(),
            })

    if not missed_runs and not short_runs:
        return {
            "has_data": True,
            "planned_miles": round(planned_total, 2),
            "actual_miles": round(actual_total, 2),
            "missed_runs": [],
            "short_runs": [],
            "summary_text": "",
            "actuals": dict(actuals),
        }

    lines = ["Training compliance gaps detected this week:"]
    for m in missed_runs:
        lines.append(f"  - {m['day'].title()} ({m['date']}): {m['planned']} mi assigned — run not completed")
    for s in short_runs:
        lines.append(
            f"  - {s['day'].title()} ({s['date']}): {s['planned']} mi assigned — "
            f"{s['actual']} mi completed (short by {round(s['planned'] - s['actual'], 2)} mi)"
        )
    lines.append(
        f"Total so far: planned {round(planned_total, 1)} mi, "
        f"completed {round(actual_total, 1)} mi for evaluated days."
    )
    lines.append(
        "Please adjust the remaining days of this week to redistribute the missed volume "
        "where appropriate, keeping the overall training structure and intensity distribution intact."
    )

    return {
        "has_data": True,
        "planned_miles": round(planned_total, 2),
        "actual_miles": round(actual_total, 2),
        "missed_runs": missed_runs,
        "short_runs": short_runs,
        "summary_text": "\n".join(lines),
        "actuals": dict(actuals),
    }
