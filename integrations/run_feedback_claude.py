"""Generate a short post-run coaching note via Claude Haiku."""
import json
from datetime import date

import anthropic

from config import Config

_SYSTEM = """\
You are a running coach writing a post-run note for an e-ink Kindle display.

Return ONLY valid JSON, no markdown fences, no explanation:
{
  "note": "<the coaching note>",
  "adjust_tomorrow": {"type": "easy"|"workout"|"long"|"rest"|"other", "distance_miles": <number>, "notes": "<short instruction>"} or null
}

NOTE FIELD: Space is EXTREMELY tight — the note must be 2 SHORT sentences and under 110 characters \
total. Count characters silently; if your draft is over 110 characters, cut words until it is not. \
Pick the 1-2 most relevant points: pace vs effort (RPE 3-4 easy / RPE 7-8 threshold), distance vs plan, \
or split consistency. Direct, specific, plain prose. No greeting, no filler, no bullets, no character \
count, no meta-commentary.

ADJUST_TOMORROW: This is the ONLY way to change tomorrow's assigned run — it directly overwrites \
tomorrow's plan entry, so it must agree with anything the note says about tomorrow. Weigh BOTH signals \
before deciding, don't react to just one:
  - How today's run actually went: pace vs prescribed effort, splits, whether it looks like overreaching.
  - This week's compliance so far: have runs already been missed or fallen short of the plan?
A short or hard-feeling run does not automatically mean back off — if the athlete is already behind on \
weekly volume, tomorrow may still need to hold its assigned load rather than stack a rest day on top of \
a deficit. Conversely, don't let a mileage deficit push make-up volume onto tomorrow if today's effort \
genuinely signals fatigue or overreaching — recovery takes priority over catching up. Set adjust_tomorrow \
only when today's run changes what tomorrow should be; if you tell the athlete to take it easy or rest \
tomorrow in the note, you MUST set adjust_tomorrow to match (e.g. type "rest", distance_miles 0), or the \
athlete will still be assigned tomorrow's original run and the note will be wrong. If tomorrow's existing \
plan is still the right call, set adjust_tomorrow to null and don't suggest changing tomorrow in the note. \
Never mention or adjust any day other than tomorrow."""


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


def _fmt_compliance(compliance: dict) -> str:
    missed = compliance.get("missed_runs") or []
    short = compliance.get("short_runs") or []
    if not missed and not short:
        return "Week compliance so far: on track, no missed or short runs.\n"
    gaps = [f"{m['day'].title()} missed ({m['planned']} mi assigned)" for m in missed]
    gaps += [f"{s['day'].title()} short ({s['actual']}/{s['planned']} mi)" for s in short]
    return (
        f"Week compliance so far: planned {compliance.get('planned_miles', 0)} mi, "
        f"completed {compliance.get('actual_miles', 0)} mi. Gaps: {'; '.join(gaps)}.\n"
    )


def generate_run_feedback(
    planned_run: dict,
    actual_run: dict,
    week_plan: dict,
    plan_meta: dict,
    today: date,
    compliance: dict | None = None,
) -> dict:
    """Return {"note": str, "adjust_tomorrow": day_dict|None}. Raises on API failure."""
    plan_type = planned_run.get("type", "run").replace("_", " ")
    plan_miles = planned_run.get("distance_miles") or 0
    plan_notes = (planned_run.get("notes") or "")[:250]

    actual_miles = actual_run.get("distance_miles") or 0
    actual_pace = actual_run.get("pace_per_mile") or "?"
    actual_time_s = actual_run.get("moving_time_s") or 0
    actual_time = _fmt_secs(int(actual_time_s)) if actual_time_s else "?"

    splits_text = _fmt_lap_splits(actual_run.get("laps") or [])

    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    tomorrow_name = DAYS[(today.weekday() + 1) % 7]
    tomorrow_plan = week_plan.get(tomorrow_name) or {}
    tomorrow_type = tomorrow_plan.get("type", "rest")
    tomorrow_miles = tomorrow_plan.get("distance_miles") or 0
    tomorrow_text = f"{tomorrow_name}: {tomorrow_type} {tomorrow_miles} mi"
    if tomorrow_plan.get("notes"):
        tomorrow_text += f" ({tomorrow_plan['notes']})"

    race_ctx = ""
    if plan_meta.get("race_name") and plan_meta.get("race_date"):
        race_ctx = f"Training for {plan_meta['race_name']} on {plan_meta['race_date']}."

    user_msg = (
        f"Planned: {plan_type}, {plan_miles} mi. Coach note: {plan_notes}\n"
        f"Actual: {actual_miles} mi in {actual_time} ({actual_pace}/mi avg)\n"
        + (f"Splits:\n{splits_text}\n" if splits_text else "(no split data)\n")
        + _fmt_compliance(compliance or {})
        + f"Currently planned for tomorrow ({tomorrow_text})\n"
        + (f"{race_ctx}\n" if race_ctx else "")
    )

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    data = json.loads(raw)
    return {
        "note": (data.get("note") or "").strip(),
        "adjust_tomorrow": data.get("adjust_tomorrow") or None,
    }
