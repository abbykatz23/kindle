import json
from datetime import date, timedelta

import anthropic

from config import Config

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_FULL_PLAN_SYSTEM = """\
You are an expert ultramarathon coach who follows evidence-based, periodized training principles.

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation, no extra text.
The JSON is an object keyed by ISO week labels (e.g. "2026-W24").
Each week maps lowercase day names (monday–sunday) to day objects. ALL 7 days must be present for every week.

Day object schema (all fields required):
{
  "type": "easy" | "workout" | "long" | "rest" | "race" | "other",
  "distance_miles": <number — 0.0 for rest days>,
  "notes": "<one short coaching note describing the run>"
}

TRAINING PRINCIPLES:
- Periodize into Base → Build → Peak → Taper phases
- Never increase total weekly mileage by more than 10% week-over-week (except step-back weeks)
- Include a step-back (recovery) week every 3–4 weeks, reducing mileage ~20%
- One long run per week, building toward 50–60% of race distance at peak (~22–26 mi)
- Back-to-back moderate-long runs in peak weeks (classic ultra prep strategy)
- At most one hard quality workout per week (tempo, progression, fartlek, or hills)
- Easy runs at conversational pace; the vast majority of weekly mileage should be easy effort
- Rest days: type must be "rest", distance_miles must be 0.0
- Race week: mark race day as type "race" with distance_miles equal to race distance; rest before and after
- 3-week taper before race: reduce mileage significantly (70% → 50% → 30% of peak)
- Injury prevention is the top priority — conservative progression beats ambitious loading
"""

_EDIT_SYSTEM = """\
You are an expert ultramarathon coach who follows evidence-based, periodized training principles.

The athlete has an existing training week they want modified. Apply their instruction while
preserving the overall training stimulus and purpose of the week.

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation, no extra text.
The JSON maps lowercase day names (monday–sunday) to day objects. ALL 7 days must be present.

Day object schema (all fields required):
{
  "type": "easy" | "workout" | "long" | "rest" | "race" | "other",
  "distance_miles": <number — 0.0 for rest days>,
  "notes": "<one short coaching note>"
}
"""


def _get_week_monday(week_label: str) -> date:
    year, wnum = week_label.split("-W")
    return date.fromisocalendar(int(year), int(wnum), 1)


def _week_label_for_date(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _weeks_from_to_race(start_label: str, race_date_str: str) -> list[str]:
    """All ISO week labels from start_label through the week containing race_date."""
    start = _get_week_monday(start_label)
    race_date = date.fromisoformat(race_date_str)
    labels = []
    cur = start
    while cur <= race_date:
        labels.append(_week_label_for_date(cur))
        cur += timedelta(weeks=1)
    return labels


def _build_history_context(plan: dict) -> str:
    running = plan.get("running", {})
    past = sorted(running.keys())[-4:]
    if not past:
        return "  No prior running history — athlete just completed a half marathon on June 5, 2026. Start base-building conservatively."
    lines = []
    for w in past:
        data = running[w]
        total = sum(d.get("distance_miles", 0.0) for d in data.values())
        types = [data.get(day, {}).get("type", "rest") for day in _DAYS]
        lines.append(f"  {w}: {round(total, 1)} mi — {', '.join(types)}")
    return "\n".join(lines)


def generate_full_running_plan(plan: dict, profile: dict, custom_prompt: str = "") -> dict:
    """Generate the complete training plan from current week through race week."""
    today = date.today()
    current_week = _week_label_for_date(today)
    race_date_str = profile.get("race_date", "2026-10-10")
    race_miles = profile.get("race_miles", 42)
    race_name = profile.get("race_name", "42-mile ultramarathon")
    days_per_week = profile.get("days_per_week_target", 4)

    week_labels = _weeks_from_to_race(current_week, race_date_str)
    num_weeks = len(week_labels)
    history = _build_history_context(plan)
    race_week_label = _week_label_for_date(date.fromisoformat(race_date_str))
    custom_section = f"\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}" if custom_prompt else ""

    week_list = "\n".join(
        f"  {wl} (Mon {_get_week_monday(wl).strftime('%b %d')})"
        for wl in week_labels
    )

    user_message = f"""\
Generate a complete {num_weeks}-week ultramarathon training plan.

ATHLETE PROFILE:
- Race: {race_name} on {race_date_str} (ISO week: {race_week_label})
- Race distance: {race_miles} miles
- Target training days per week: {days_per_week} (rest the remaining days)
- Current fitness: just completed a half marathon on June 5, 2026 — solid aerobic base, needs short recovery

RECENT TRAINING HISTORY:
{history}

WEEKS TO PLAN (every week must appear in the output JSON):
{week_list}

PERIODIZATION GUIDANCE:
- Weeks 1–2: recovery from half marathon, easy running 25–30 mi/week
- Weeks 3–8: base building, build to 35–40 mi/week
- Weeks 9–14: build phase, quality workouts, 40–50 mi/week with step-back weeks
- Weeks 15–17: peak, 50–55 mi/week, back-to-back long runs
- Final 3 weeks: taper — reduce to ~70%, ~50%, ~30% of peak
- Race week: mark race day ({race_date_str}) as type "race"
{custom_section}
"""

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=_FULL_PLAN_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def edit_weekly_running_plan(
    week_label: str,
    plan: dict,
    profile: dict,
    custom_prompt: str = "",
) -> dict:
    """Edit a specific week's plan based on the user's instruction."""
    race_date_str = profile.get("race_date", "2026-10-10")
    race_miles = profile.get("race_miles", 42)
    race_name = profile.get("race_name", "42-mile ultramarathon")

    existing_week = plan.get("running", {}).get(week_label, {})
    if existing_week:
        existing_lines = []
        for day in _DAYS:
            d = existing_week.get(day, {})
            line = f"  {day}: {d.get('type', 'rest')} — {d.get('distance_miles', 0)} mi"
            if d.get("notes"):
                line += f" ({d['notes']})"
            existing_lines.append(line)
        existing_text = "\n".join(existing_lines)
    else:
        existing_text = "  No plan yet for this week — create a reasonable week given the race context."

    monday = _get_week_monday(week_label)
    race_date = date.fromisoformat(race_date_str)
    weeks_to_race = max(0, round((race_date - monday).days / 7))

    user_message = f"""\
Modify the training plan for {week_label} (week of {monday.strftime('%b %d, %Y')}).

RACE CONTEXT: {race_name} on {race_date_str} ({weeks_to_race} weeks away, {race_miles} miles)

CURRENT PLAN:
{existing_text}

USER INSTRUCTION:
{custom_prompt if custom_prompt else "No specific instruction — produce a solid week consistent with this point in training."}

Apply the instruction while preserving the week's overall training stimulus. \
If relocating a run type, keep its distance and character. \
Do not dramatically change total weekly mileage unless the instruction requires it.
"""

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_EDIT_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)
