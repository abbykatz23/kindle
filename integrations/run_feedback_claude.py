"""Generate a short post-run coaching note via Claude Haiku."""
import anthropic

from config import Config

_SYSTEM = """\
You are a running coach writing a post-run note for an e-ink Kindle display. \
Space is EXTREMELY tight: your ENTIRE response must be 2 SHORT sentences and under 110 characters total. \
Count your characters. If your draft is over 110 characters, cut words until it is not.

Pick the 1-2 most relevant points: pace vs effort (RPE 3-4 easy / RPE 7-8 threshold), \
distance vs plan, split consistency, or week adjustment if something was off. \
Direct, specific, plain prose. No greeting, no filler, no bullets."""


def _fmt_secs(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_lap_splits(laps: list[dict]) -> str:
    lines = []
    for i, lap in enumerate(laps[:6]):
        dist_m = lap.get("distance") or 0
        time_s = lap.get("moving_time") or 0
        if dist_m < 800 or time_s <= 0:
            continue
        dist_mi = dist_m / 1609.344
        pace_s = time_s / dist_mi
        pace_m, pace_sec = int(pace_s) // 60, int(pace_s) % 60
        lines.append(f"  Split {i + 1}: {dist_mi:.2f} mi @ {pace_m}:{pace_sec:02d}/mi")
    return "\n".join(lines) if lines else ""


def generate_run_feedback(
    planned_run: dict,
    actual_run: dict,
    week_plan: dict,
    plan_meta: dict,
) -> str:
    """Return 2-3 sentence coaching note. Raises on API failure."""
    plan_type = planned_run.get("type", "run").replace("_", " ")
    plan_miles = planned_run.get("distance_miles") or 0
    plan_notes = (planned_run.get("notes") or "")[:250]

    actual_miles = actual_run.get("distance_miles") or 0
    actual_pace = actual_run.get("pace_per_mile") or "?"
    actual_time_s = actual_run.get("moving_time_s") or 0
    actual_time = _fmt_secs(int(actual_time_s)) if actual_time_s else "?"

    splits_text = _fmt_lap_splits(actual_run.get("laps") or [])

    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    remaining = []
    for day in DAYS:
        d = week_plan.get(day) or {}
        if d.get("type") not in (None, "rest") and (d.get("distance_miles") or 0) > 0:
            remaining.append(f"{day}: {d['type']} {d['distance_miles']} mi")

    race_ctx = ""
    if plan_meta.get("race_name") and plan_meta.get("race_date"):
        race_ctx = f"Training for {plan_meta['race_name']} on {plan_meta['race_date']}."

    user_msg = (
        f"Planned: {plan_type}, {plan_miles} mi. Coach note: {plan_notes}\n"
        f"Actual: {actual_miles} mi in {actual_time} ({actual_pace}/mi avg)\n"
        + (f"Splits:\n{splits_text}\n" if splits_text else "(no split data)\n")
        + (f"Rest of week: {', '.join(remaining)}\n" if remaining else "No other runs planned this week.\n")
        + (f"{race_ctx}\n" if race_ctx else "")
    )

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=180,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return msg.content[0].text.strip()
