import json
from datetime import date, timedelta

import anthropic

from config import Config

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# ── Core science ──────────────────────────────────────────────────────────────

_SEILER_FRAMEWORK = """\
TRAINING PHILOSOPHY — POLARIZED INTENSITY DISTRIBUTION:

Stephen Seiler's research across elite endurance athletes consistently finds that ~80%
of training volume should be at LOW intensity and ~20% at HIGH intensity, with very
little in between. This is the most rigorously studied intensity model in endurance sport.

THREE INTENSITY LEVELS:

  EASY (RPE 3–4/10, ~80% of all training):
    - Full conversational sentences throughout — you could recite a paragraph out loud
    - Could nose-breathe the whole run if you wanted to
    - This is genuinely slow, often slower than athletes expect. That is correct.
    - Builds aerobic base: mitochondrial density, fat oxidation, cardiac output

  MODERATE (RPE 5–6/10) — AVOID:
    - The "grey zone": too hard for aerobic base gains, too easy for speed gains
    - Accumulates fatigue without meaningful adaptation
    - Most recreational runners spend too much time here because it feels productive
    - If a run is supposed to be easy, it should be genuinely easy, not moderate

  HARD / THRESHOLD (RPE 7–9/10, ~20% of all training):
    - Comfortably hard — a few words possible between breaths, not full sentences
    - Tempo runs, threshold repeats, hill intervals
    - Only in build and peak phases, at most once per week

THE KEY RULE: If it's easy, make it genuinely easy. If it's hard, make it genuinely hard.
Never drift into the moderate middle.

LONG RUNS:
Always at easy effort (RPE 3–4) — slow enough to hold a full conversation. Long runs
build aerobic infrastructure and connective tissue resilience. For ultras, time on feet
is the stimulus, not pace: a 3-hour easy run is more valuable than a 2-hour moderate one.
"""

_VDOT_FRAMEWORK = """\
VDOT TRAINING PACES (Jack Daniels' system — use for marathon and shorter only):

VDOT derives athlete-specific training paces from a recent race result. This anchors
every workout to current fitness rather than aspirational targets.

STEP 1 — Compute race pace per mile:
  race_pace_sec = finish_time_in_seconds / race_miles

STEP 2 — Convert to marathon-equivalent pace (MP):
  Marathon (26.2 mi):     MP = race_pace_sec
  Half marathon (13.1 mi): MP = race_pace_sec × 1.08
  10K (6.21 mi):          MP = race_pace_sec × 1.15
  5K (3.11 mi):           MP = race_pace_sec × 1.22
  1 mile:                 MP = race_pace_sec × 1.40

STEP 3 — Derive training paces from MP (seconds per mile):
  Easy (E)  / Zone 1:    MP + 75–90s   (use +90s for newer/lower-mileage runners)
  Marathon (M) pace:     MP            (race-specific sessions in peak phase only)
  Threshold (T) / tempo: MP − 40s      (Zone 3 tempo, ~lactate threshold)
  Interval (I):          MP − 75s      (Zone 3 repeats, ~5K race effort)
  Repetition (R):        MP − 110s     (strides and short reps, ~mile effort)

STEP 4 — Express all paces as MM:SS/mi in workout notes.

Example: 10K in 50:00 (8:03/mi)
  MP ≈ 8:03 × 1.15 = 9:16/mi (556 sec)
  Easy:       10:46–11:01/mi
  Marathon:   9:16/mi
  Threshold:  8:36/mi
  Interval:   8:01/mi
  Reps/strides: 7:26/mi

SEILER ↔ VDOT MAPPING:
  Zone 1 easy runs = E pace
  Zone 3 tempo runs = T pace
  Zone 3 interval repeats = I pace
  Strides = R pace
  Marathon-pace miles (final miles of long run, peak phase only) = M pace

If no recent race result was provided, estimate conservatively from the athlete's
stated current weekly mileage and experience. State the assumed VDOT basis in the
first week's notes so the athlete can verify.
"""

_PERIODIZATION_PRINCIPLES = """\
PERIODIZATION AND PROGRESSION:

Progressive overload:
  - Increase weekly mileage no more than 10% week-over-week
  - Cutback (recovery) week every 3–4 weeks: reduce mileage ~20–25%
  - Adaptation happens during recovery, not during the hard weeks
  - Pattern: build → build → build → cut back → build higher → repeat

Phases:
  Base (~40% of training cycle): Zone 1 only. No quality sessions.
    Build aerobic infrastructure. This phase is longer than most athletes want.
  Build (~35%): Introduce one Zone 3 quality session per week.
    Mileage continues to grow. Quality sessions earn their place because the base
    is now large enough to absorb them.
  Peak (~15%): Highest mileage. Back-to-back long runs for ultras.
    One quality session/week. Race-specific simulation.
  Taper (final 3 weeks): 70% → 50% → 30% of peak weekly volume.
    Maintain SOME intensity (don't go all-easy — detraining starts in 10 days).

Ultra-specific protocols:
  - Back-to-back long runs in peak phase (e.g. 15mi Sat + 10mi Sun): running on
    tired legs simulates the back half of a 50-mile race
  - Measure long runs by time, not miles — "3 hours easy" beats "20 miles"
  - Practice power hiking uphills — this is a genuine racing skill for ultras,
    not a fallback; elites walk the steep climbs by design
  - Nutrition practice during any run over 75–90 minutes
  - Peak long run should reach ~70% of race distance (e.g. 29 mi for a 42-mile race, 35 mi for a 50-mile race)

Taper science:
  - Three-week taper is well-supported by research
  - Volume drops but intensity stays — do NOT go all-easy in taper
  - Last long run 3 weeks before race; nothing over 14–16 miles after that
  - Complete rest 1–2 days before race

Injury prevention:
  - The most common cause of overuse injury is too-rapid mileage increases
  - Easy runs being too fast is the second most common cause
  - Two hard sessions on consecutive days: never
  - After any race, allow 1 easy recovery week before resuming normal training
"""

# ── System prompts ────────────────────────────────────────────────────────────

_QUESTIONS_SYSTEM = """\
You are an elite running coach conducting a brief intake interview before designing
a personalized training plan. The athlete has filled out a basic intake form.

Ask 3–4 targeted questions that would most meaningfully improve the plan.
Do NOT re-ask things already covered in the intake. Focus on high-impact unknowns.

DO NOT ask about:
- Current weekly mileage or recent training volume — this is pulled automatically from
  GPS activity data and is already available
- General fitness level in terms of mileage — use qualitative questions instead
- How many miles per week they run — already known from activity tracking

Prioritize in this order:
1. Recent race result (if training for marathon or shorter and not provided) — essential
   for calculating VDOT training paces. E.g.: "What's your most recent race result?
   Please include the distance and finish time (e.g. 10K in 52:30)."
2. Injury history — recurring issues that constrain training choices (IT band, Achilles,
   stress fractures). What aggravates them and what modifications help.
3. Schedule constraints — specific days that are off-limits, work travel, early mornings
   vs evenings, any weeks with unusual schedules.
4. Terrain (especially for ultras) — trails vs roads, typical elevation in training runs,
   race course profile (e.g. "mostly flat" vs "10,000ft gain").
5. Tune-up races — any shorter races planned during the training cycle.
6. Training background — what has worked or caused problems in past training cycles
   (NOT mileage-based — focus on structure, intensity, injury patterns).

FORMAT: Return a plain numbered list. No preamble. No sign-off.
1. ...
2. ...
3. ...
4. ... (optional)
"""

_SKELETON_SYSTEM = f"""\
You are an expert endurance running coach designing a periodized training plan skeleton.

{_SEILER_FRAMEWORK}

{_PERIODIZATION_PRINCIPLES}

Your task: given an athlete profile, produce a week-by-week mileage and structure plan.
This skeleton will be reviewed and then used to generate a full daily training schedule.

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation.
Keys are week number strings ("1", "2", ...). All weeks must be present.

Week object schema:
{{
  "phase": "base" | "build" | "peak" | "taper" | "race",
  "weekly_miles": <number>,
  "long_run_miles": <number>,
  "quality_sessions": <0 or 1>
}}

Rules:
- Base phase: quality_sessions = 0 always
- Build/peak: quality_sessions = 1 (one Zone 3 session per week, never two)
- Taper: weekly_miles drops to ~70% / ~50% / ~30% of peak over 3 weeks; quality_sessions = 1
- Race week: phase = "race", weekly_miles = minimal (race day + easy shakeout only)
- Never increase weekly_miles > 10% week-over-week
- Include a cutback week (20–25% reduction) every 3–4 weeks
- long_run_miles in the peak phase MUST reach 70% of race distance — this is a hard requirement
"""

_CRITIQUE_SYSTEM = """\
You are a sports science reviewer evaluating a running training plan skeleton for safety,
scientific soundness, and alignment with polarized training research.

Check the following and flag any issues:
1. Weekly mileage progression: does any week increase >10% over the prior week?
2. Cutback weeks: is there a recovery week (20–25% reduction) at least every 4 weeks?
3. Phase distribution: is the base phase at least 35–40% of total weeks?
4. Quality sessions: are they zero during base, and no more than one per week after?
5. Taper: do the final 3 weeks before the race show roughly 70%/50%/30% of peak mileage?
6. Starting mileage: is it reasonable given the athlete's stated current mileage?
7. Peak mileage: does it realistically follow from the starting point?
8. Long run: does it reach ~70% of race distance at peak? Flag if it falls below 65%.

Be specific. Name the exact week numbers if you flag an issue.
If the skeleton looks good, say so briefly. Keep your response under 300 words.
"""

_FULL_PLAN_SYSTEM_BASE = f"""\
You are an elite endurance running coach with deep expertise in exercise physiology.

{_SEILER_FRAMEWORK}

{_PERIODIZATION_PRINCIPLES}

You will receive a validated periodization skeleton (weekly mileage targets and phase
labels) plus a science review of that skeleton. Your job is to fill in the daily detail
— specific workouts for each day of each week — while respecting the skeleton's structure.

QUALITY SESSION TYPES (Zone 3, used only in build and peak phases, one per week max):
  - Tempo run: 20–40 min at comfortably hard effort (LT2 pace, ~RPE 7/10)
  - Hill repeats: 6–10 × 60–90s uphill hard, walk/jog recovery
  - Progression run: start easy, finish the last 15–20 min at tempo effort
  - (For ultras) Long hill repeat: 3–4 × 10–15 min moderate uphill at effort

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation, no extra text.
Keys are week number strings ("1", "2", ...). All weeks must appear.
Each week maps lowercase day names (monday–sunday) to day objects. All 7 days required.

Day object schema:
{{
  "type": "easy" | "workout" | "long" | "rest" | "race" | "other",
  "distance_miles": <number — 0.0 for rest days>,
  "notes": "<specific, concrete coaching instruction for this run>"
}}
"""

_COACH_SYSTEM = f"""\
You are a running coach making targeted adjustments to an athlete's active training plan.

{_SEILER_FRAMEWORK}

RULES:
1. Make ONLY the minimum changes needed to address the athlete's message.
2. Preserve the overall weekly training load and 80/20 intensity split.
3. Never place two Zone 3 quality sessions on consecutive days.
4. If the message reveals a lasting signal (injury, constraint, preference), set persistent_note.
5. You may adjust the current week and the next 1–2 weeks only.
6. Preserve any notes_actual fields — do not include them in your output.

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "changes": {{
    "<week_num_string>": {{
      "<day_name>": {{
        "type": "easy" | "workout" | "long" | "rest" | "race" | "other",
        "distance_miles": <number>,
        "notes": "<specific coaching instruction>"
      }}
    }}
  }},
  "feedback": "<1–3 sentences: what you changed and why, or why no change was needed>",
  "persistent_note": "<one-sentence lasting signal, or null>"
}}

Include only weeks and days that actually changed.
"""

_EDIT_SYSTEM = f"""\
You are an elite endurance running coach following polarized training principles:
~80% of volume at easy effort (RPE 3–4, conversational, full sentences throughout),
~20% at hard/threshold effort (RPE 7–9, comfortably hard), avoiding the moderate
"grey zone" (RPE 5–6) that accumulates fatigue without meaningful gains.

Apply the athlete's modification to the existing training week while preserving
its overall training stimulus. Do not shift the intensity distribution.
Use RPE targets and effort descriptors in notes — no zone number labels.

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation.
Map lowercase day names (monday–sunday) to day objects. All 7 days required.

Day object schema:
{{
  "type": "easy" | "workout" | "long" | "rest" | "race" | "other",
  "distance_miles": <number — 0.0 for rest days>,
  "notes": "<specific coaching instruction>"
}}
"""


def _build_full_plan_system(use_vdot: bool) -> str:
    if use_vdot:
        pace_section = (
            f"\n{_VDOT_FRAMEWORK}\n"
            "PACE PRESCRIPTION REQUIREMENT:\n"
            "This athlete is training for a marathon or shorter. Every workout note MUST\n"
            "include a specific target pace in MM:SS/mi derived from the VDOT calculation\n"
            "above. Examples: '6 miles at easy pace (10:45/mi)' or '2mi warmup, 4×1mi at\n"
            "T-pace (8:35/mi) with 90s jog recovery, 2mi cooldown'. No vague effort cues\n"
            "without a pace — the athlete is following VDOT and needs numbers.\n"
            "For long runs in peak phase: include optional marathon-pace miles at the end\n"
            "(e.g. 'last 3 miles at M-pace (9:16/mi)') to build race-specific feel.\n"
        )
    else:
        pace_section = (
            "\nINTENSITY PRESCRIPTION:\n"
            "This is ultra or general fitness training. Every workout note MUST include\n"
            "an RPE target and an effort descriptor — no zone numbers. Examples:\n"
            "  Easy run: 'RPE 3-4, conversational throughout — full sentences, not breathless'\n"
            "  Long run: '2.5 hours at easy effort (RPE 3-4), power hike anything steep'\n"
            "  Tempo: 'RPE 7-8, comfortably hard — a few words between breaths'\n"
            "  Hill repeats: '6 × 60s uphill hard (RPE 8), walk back down to recover'\n"
            "For long runs prescribe time, not miles. Pace is secondary to effort and time.\n"
        )
    return _FULL_PLAN_SYSTEM_BASE + pace_section


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_plan_week_monday(start_date_str: str, week_num: int) -> date:
    start = date.fromisoformat(start_date_str)
    start_monday = start - timedelta(days=start.weekday())
    return start_monday + timedelta(weeks=(week_num - 1))


def _total_plan_weeks(start_date_str: str, race_date_str: str) -> int:
    start = date.fromisoformat(start_date_str)
    start_monday = start - timedelta(days=start.weekday())
    race = date.fromisoformat(race_date_str)
    return max(1, ((race - start_monday).days // 7) + 1)


def _parse_intake(intake: dict) -> dict:
    today = date.today()
    start_date = intake.get("start_date") or today.isoformat()
    race_date_str = intake.get("race_date", "").strip()
    race_name = intake.get("race_name", "").strip()
    race_distance_unit = intake.get("race_distance_unit", "miles")
    notes = intake.get("notes", "").strip()
    recent_race_result = intake.get("recent_race_result", "").strip()
    qa_context = intake.get("qa_context", "").strip()
    training_history = intake.get("training_history", "").strip()
    race_results_context = intake.get("race_results_context", "").strip()

    try:
        days_per_week = int(intake.get("days_per_week") or 4)
    except (TypeError, ValueError):
        days_per_week = 4

    try:
        race_miles = float(intake.get("race_miles") or 0)
        if race_distance_unit == "km":
            race_miles = round(race_miles * 0.621371, 1)
    except (TypeError, ValueError):
        race_miles = 0

    try:
        current_mileage = float(intake.get("current_weekly_mileage") or 0)
    except (TypeError, ValueError):
        current_mileage = 0

    if race_date_str:
        num_weeks = _total_plan_weeks(start_date, race_date_str)
        start_dt = date.fromisoformat(start_date)
        start_monday = start_dt - timedelta(days=start_dt.weekday())
        race_dt = date.fromisoformat(race_date_str)
        race_week_num = max(1, ((race_dt - start_monday).days // 7) + 1)
    else:
        num_weeks = 16
        race_week_num = None

    use_vdot = race_miles > 0 and race_miles <= 26.2

    return {
        "start_date": start_date,
        "race_date_str": race_date_str,
        "race_name": race_name,
        "race_miles": race_miles,
        "days_per_week": days_per_week,
        "current_mileage": current_mileage,
        "notes": notes,
        "recent_race_result": recent_race_result,
        "qa_context": qa_context,
        "num_weeks": num_weeks,
        "race_week_num": race_week_num,
        "use_vdot": use_vdot,
        "training_history": training_history,
        "race_results_context": race_results_context,
    }


def _athlete_profile_text(p: dict) -> str:
    lines = []
    if p["race_name"] and p["race_date_str"] and p["race_miles"]:
        lines.append(f"- Race: {p['race_name']} on {p['race_date_str']} ({p['race_miles']} miles) — Week {p['race_week_num']}")
    elif p["race_date_str"]:
        lines.append(f"- Goal event on {p['race_date_str']} — Week {p['race_week_num']}")
    else:
        lines.append("- No specific race — general ultra fitness training")
    lines.append(f"- Training methodology: {'VDOT pace-based (marathon or shorter)' if p['use_vdot'] else 'Seiler effort-based (ultra / general fitness)'}")
    lines.append(f"- Training days: {p['days_per_week']}/week ({7 - p['days_per_week']} rest days)")
    if p["current_mileage"]:
        lines.append(f"- Current weekly mileage: {p['current_mileage']} mi")
    else:
        lines.append("- Current mileage: not specified (assume conservative start)")
    if p["recent_race_result"]:
        lines.append(f"- Recent race result: {p['recent_race_result']}")
    if p["notes"]:
        lines.append(f"- Additional context: {p['notes']}")
    if p.get("race_results_context"):
        lines.append(f"\nRACE RESULTS (max effort — use for VDOT pace calibration):\n{p['race_results_context']}")
    if p["qa_context"]:
        lines.append(f"\nINTAKE Q&A:\n{p['qa_context']}")
    if p["training_history"]:
        lines.append(f"\n{p['training_history']}")
    return "\n".join(lines)


def _week_list_text(p: dict) -> str:
    lines = []
    for wnum in range(1, p["num_weeks"] + 1):
        mon = _get_plan_week_monday(p["start_date"], wnum)
        lines.append(f"  Week {wnum} (Mon {mon.strftime('%b %d')})")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> dict:
    import re
    raw = raw.strip()
    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    # If still not starting with {, extract the first JSON object found
    if not raw.startswith("{"):
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            raw = match.group(0)
    return json.loads(raw)


# ── Intake questions ──────────────────────────────────────────────────────────

def generate_intake_questions(intake: dict) -> str:
    """Synchronous Sonnet call — asks targeted questions before plan generation."""
    p = _parse_intake(intake)
    user_message = (
        f"Athlete intake:\n{_athlete_profile_text(p)}\n\n"
        f"What additional information would most improve this athlete's training plan?"
    )
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=_QUESTIONS_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text.strip()


# ── Three-pass plan generation ────────────────────────────────────────────────

def _generate_skeleton(p: dict, client: anthropic.Anthropic) -> dict:
    num_weeks = p["num_weeks"]
    base_end = max(1, round(num_weeks * 0.40))
    build_end = max(base_end + 1, round(num_weeks * 0.75))
    peak_end = max(build_end + 1, num_weeks - 3)

    guidance = (
        f"Periodization boundaries ({num_weeks} weeks):\n"
        f"  Weeks 1–{base_end}: base (quality_sessions=0)\n"
        f"  Weeks {base_end+1}–{build_end}: build (quality_sessions=1)\n"
        f"  Weeks {build_end+1}–{peak_end}: peak (quality_sessions=1)\n"
        f"  Weeks {peak_end+1}–{num_weeks}: taper/race"
    )
    if p["race_week_num"]:
        guidance += f"\n  Week {p['race_week_num']}: race week"

    if p["race_miles"] and p["race_miles"] > 0:
        target_long = round(p["race_miles"] * 0.70, 1)
        guidance += (
            f"\n\nLONG RUN REQUIREMENT: Peak long_run_miles MUST reach {target_long} miles "
            f"(70% of the {p['race_miles']}-mile race). This is non-negotiable. "
            f"The peak long run should appear in the peak phase, not taper."
        )

    user_message = (
        f"Generate a periodization skeleton for {num_weeks} weeks.\n\n"
        f"ATHLETE:\n{_athlete_profile_text(p)}\n\n"
        f"{guidance}\n\n"
        f"WEEKS:\n{_week_list_text(p)}"
    )

    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=_SKELETON_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text"))
    return _parse_json_response(raw)


def _critique_skeleton(skeleton: dict, p: dict, client: anthropic.Anthropic) -> str:
    skeleton_lines = []
    for wnum in range(1, p["num_weeks"] + 1):
        w = skeleton.get(str(wnum), {})
        skeleton_lines.append(
            f"  Week {wnum}: {w.get('phase','?')} — {w.get('weekly_miles','?')} mi total, "
            f"{w.get('long_run_miles','?')} mi long run, "
            f"{w.get('quality_sessions','?')} quality session(s)"
        )

    user_message = (
        f"Review this {p['num_weeks']}-week training skeleton for an athlete with:\n"
        f"{_athlete_profile_text(p)}\n\n"
        f"SKELETON:\n" + "\n".join(skeleton_lines)
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=_CRITIQUE_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text.strip()


def generate_full_running_plan(intake: dict, progress_cb=None) -> dict:
    """Three-pass plan generation.

    Pass 1 (Opus + thinking): periodization skeleton
    Pass 2 (Sonnet): sports science critique
    Pass 3 (Opus + thinking + streaming): full daily plan using skeleton + critique
    """
    def progress(msg):
        if progress_cb:
            progress_cb(msg)

    # Fetch real training history from intervals.icu (no-op if unavailable)
    progress("Fetching training history from intervals.icu...")
    try:
        from integrations.intervals_api import get_training_context
        training_history = get_training_context()
    except Exception:
        training_history = ""
    if training_history:
        intake = {**intake, "training_history": training_history}

    # Include race results for VDOT calibration
    try:
        from utils.race_results import race_results_context
        race_ctx = race_results_context()
        if race_ctx and race_ctx != "None":
            intake = {**intake, "race_results_context": race_ctx}
    except Exception:
        pass

    p = _parse_intake(intake)
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    full_plan_system = _build_full_plan_system(p["use_vdot"])

    progress("Building periodization structure...")
    try:
        skeleton = _generate_skeleton(p, client)
    except Exception:
        skeleton = {}

    progress("Running sports science review...")
    try:
        critique = _critique_skeleton(skeleton, p, client)
    except Exception:
        critique = ""

    progress("Generating detailed daily schedule...")

    skeleton_text = ""
    if skeleton:
        skeleton_lines = []
        for wnum in range(1, p["num_weeks"] + 1):
            w = skeleton.get(str(wnum), {})
            if w:
                skeleton_lines.append(
                    f"  Week {wnum}: {w.get('phase','?')} — {w.get('weekly_miles','?')} mi, "
                    f"{w.get('long_run_miles','?')} mi long run, "
                    f"{w.get('quality_sessions','?')} quality session(s)"
                )
        if skeleton_lines:
            skeleton_text = "PERIODIZATION SKELETON (use as constraints for daily detail):\n" + "\n".join(skeleton_lines)

    critique_text = f"\nSPORTS SCIENCE REVIEW:\n{critique}" if critique else ""

    # Identify past days in Week 1 that must be rest (plan starts mid-week)
    start_dt = date.fromisoformat(p["start_date"])
    week1_monday = start_dt - timedelta(days=start_dt.weekday())
    past_days_note = ""
    if start_dt > week1_monday:
        past_days = [_DAYS[i] for i in range(start_dt.weekday())]
        past_days_note = (
            f"\nIMPORTANT — Week 1 starts mid-week: the plan begins on "
            f"{start_dt.strftime('%A %b %d')}. The following days are already in the past "
            f"and MUST be set as rest days (distance_miles: 0): "
            f"{', '.join(past_days)}. Do not assign any runs to these days.\n"
        )

    user_message = (
        f"Generate a complete {p['num_weeks']}-week daily training plan.\n\n"
        f"ATHLETE:\n{_athlete_profile_text(p)}\n\n"
        f"{skeleton_text}"
        f"{critique_text}"
        f"{past_days_note}\n\n"
        f"WEEKS (all must appear as keys in output JSON):\n{_week_list_text(p)}"
    )

    with client.messages.stream(
        model=Config.CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=full_plan_system,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        message = stream.get_final_message()

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text"))
    return _parse_json_response(raw)


# ── Per-week edit ─────────────────────────────────────────────────────────────

def edit_weekly_running_plan(
    week_num: int,
    active_plan: dict,
    custom_prompt: str = "",
) -> dict:
    race_date_str = active_plan.get("race_date", "")
    race_miles = active_plan.get("race_miles", 0)
    race_name = active_plan.get("race_name", "")
    start_date = active_plan.get("start_date", date.today().isoformat())

    existing_week = active_plan.get("weeks", {}).get(str(week_num), {})
    if existing_week:
        lines = []
        for day in _DAYS:
            d = existing_week.get(day, {})
            line = f"  {day}: {d.get('type', 'rest')} — {d.get('distance_miles', 0)} mi"
            if d.get("notes"):
                line += f" ({d['notes']})"
            lines.append(line)
        existing_text = "\n".join(lines)
    else:
        existing_text = "  No plan yet — create a reasonable week consistent with the training phase."

    monday = _get_plan_week_monday(start_date, week_num)
    weeks_to_race = None
    if race_date_str:
        race_dt = date.fromisoformat(race_date_str)
        weeks_to_race = max(0, (race_dt - monday).days // 7)

    if race_name and race_date_str:
        race_ctx = f"Race: {race_name} on {race_date_str} ({weeks_to_race} weeks away, {race_miles} miles)"
    elif race_date_str:
        race_ctx = f"Goal event on {race_date_str} ({weeks_to_race} weeks away)"
    else:
        race_ctx = "General fitness training (no specific race)"

    user_message = (
        f"Modify training plan Week {week_num} (week of {monday.strftime('%b %d, %Y')}).\n\n"
        f"{race_ctx}\n\n"
        f"Current plan:\n{existing_text}\n\n"
        f"Athlete instruction:\n"
        f"{custom_prompt or 'No specific instruction — produce a solid week consistent with the training phase.'}\n\n"
        f"Keep the overall weekly training stimulus intact. Preserve the 80/20 intensity split. "
        f"If moving a run, preserve its distance and character."
    )

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_EDIT_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text"))
    return _parse_json_response(raw)


# ── Live coach ────────────────────────────────────────────────────────────────

def coach_running_plan(
    active_plan: dict,
    current_week_num: int,
    user_message: str,
    race_results_ctx: str = "",
    coaching_notes_ctx: str = "",
) -> dict:
    """Make targeted adjustments to the running plan based on prose user message.

    Returns {"changes": {week_num_str: {day: {...}}}, "feedback": str, "persistent_note": str|None}
    """
    weeks_ctx = []
    for wnum in range(max(1, current_week_num - 1), current_week_num + 3):
        week = active_plan.get("weeks", {}).get(str(wnum))
        if not week:
            continue
        label = f"Week {wnum}" + (" (current)" if wnum == current_week_num else "")
        weeks_ctx.append(label + ":")
        for day in _DAYS:
            d = week.get(day, {})
            run_type = d.get("type", "rest")
            if run_type == "rest" or not d.get("distance_miles"):
                weeks_ctx.append(f"  {day}: rest")
            else:
                line = f"  {day}: {run_type} {d.get('distance_miles')}mi"
                if d.get("notes"):
                    line += f" — {d['notes']}"
                if d.get("notes_actual"):
                    line += f" [actual: {d['notes_actual']}]"
                weeks_ctx.append(line)

    user_msg = (
        f"Current plan week: {current_week_num}\n\n"
        f"PLAN:\n" + "\n".join(weeks_ctx) + "\n\n"
        f"RACE RESULTS (all max effort, use for VDOT pacing):\n{race_results_ctx or 'None'}\n\n"
        f"PERSISTENT COACHING NOTES:\n{coaching_notes_ctx or 'None'}\n\n"
        f"ATHLETE MESSAGE:\n{user_message}"
    )

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=_COACH_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = next((b.text for b in reversed(message.content) if hasattr(b, "text")), "")
    if not raw:
        raise ValueError("Claude returned an empty response")
    return _parse_json_response(raw)
