import json
from datetime import date, datetime, timedelta

import anthropic

from config import Config

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_SYSTEM_PROMPT_TEMPLATE = """\
You are a technical interview prep coach generating a weekly study plan for a software engineering candidate targeting Google-level companies.

GOAL: {goal}

RESOURCES AVAILABLE:
{resources}

PROBLEM SET APPROACH: {problem_set}

CURRICULUM PHASES:
{phases}

LeetCode TOPIC ORDER (follow this sequence across weeks — don't jump ahead):
{topic_order}

BEHAVIORAL STORIES TO DEVELOP (target: {behavioral_target} total):
{behavioral_themes}

OUTPUT FORMAT:
Return ONLY valid JSON — no markdown fences, no explanation, no extra text.
The JSON maps lowercase day names (monday–sunday) to arrays of task objects.
Omit days with no tasks entirely.

Task object schema (all fields required):
{{
  "type": "leetcode" | "system_design" | "behavioral" | "reading" | "other",
  "task": "string — see formatting rules below",
  "leetcode_slug": "the-problem-slug" | null,
  "completed": false
}}

TASK FORMATTING RULES:
- leetcode: "#NNN Problem Title" — use the real problem number and title. leetcode_slug must be the real URL slug.
- reading: Name the book and specific chapter/section. Example: "OSTEP ch 5-6: Process API and Direct Execution"
- system_design: Be specific. Example: "Alex Xu ch 5: Design consistent hashing" or "Mock design: YouTube from scratch (no reference)"
- behavioral: Name the specific STAR story theme. Example: "Write STAR story: disagreement with a teammate"
- other: Be specific about what to do.

CARRY-OVER RULES:
If there are overdue tasks listed below, include them in this week's plan FIRST, before adding any new material.
When carrying over a task, append " (carry-over from {placeholder_week})" to the task string — replace {placeholder_week} with the actual week label.
Keep the original type and leetcode_slug.
If there are many overdue tasks, reduce new material proportionally. A lighter week that actually gets done is better than an overloaded one that doesn't.\
"""


def _get_week_monday(week_label: str) -> date:
    year, wnum = week_label.split("-W")
    return date.fromisocalendar(int(year), int(wnum), 1)


def _build_context(week_label: str, plan: dict, curriculum: dict) -> dict:
    start_date = date.fromisoformat(curriculum["start_date"])
    monday = _get_week_monday(week_label)
    week_num = max(1, (monday - start_date).days // 7 + 1)
    total_weeks = curriculum["total_weeks"]

    current_phase = curriculum["phases"][-1]
    for phase in curriculum["phases"]:
        if phase["weeks_start"] <= week_num <= phase["weeks_end"]:
            current_phase = phase
            break

    interview_prep = plan.get("interview_prep", {})
    past_weeks = sorted(w for w in interview_prep if w < week_label)

    total_assigned = 0
    total_completed = 0
    overdue_tasks = []
    recent_summaries = []

    for w in past_weeks:
        days_data = interview_prep[w]
        week_assigned = 0
        week_completed = 0
        for day in _DAYS:
            for task in days_data.get(day, []):
                week_assigned += 1
                total_assigned += 1
                if task.get("completed"):
                    week_completed += 1
                    total_completed += 1
                else:
                    overdue_tasks.append({
                        "week": w,
                        "day": day,
                        "type": task.get("type", "other"),
                        "task": task.get("task", ""),
                        "leetcode_slug": task.get("leetcode_slug"),
                    })
        recent_summaries.append({
            "week": w,
            "assigned": week_assigned,
            "completed": week_completed,
        })

    recent_summaries = recent_summaries[-3:]

    if total_assigned == 0:
        completion_pct = 100
        status = "no history yet — this is the first week"
    else:
        completion_pct = round(total_completed / total_assigned * 100)
        if completion_pct >= 90:
            status = "on track"
        elif completion_pct >= 70:
            status = "slightly behind — carry-over tasks should be prioritized"
        else:
            status = "significantly behind — prioritize carry-over tasks and reduce new material this week"

    # Slugs already present in the target week (inserted by nightly carryover — don't re-add)
    target_week_data = interview_prep.get(week_label, {})
    already_in_week_slugs: set[str] = set()
    for day in _DAYS:
        for task in target_week_data.get(day, []):
            if task.get("leetcode_slug") and task.get("type") == "leetcode":
                already_in_week_slugs.add(task["leetcode_slug"])

    # Filter overdue list: exclude slugs that are already carried into this week
    overdue_tasks = [t for t in overdue_tasks if t.get("leetcode_slug") not in already_in_week_slugs]

    # Ahead-of-schedule completions from nightly state update
    from utils.state import load_state
    ahead_slugs: set[str] = set(load_state().get("leetcode_ahead", []))

    # Persistent coaching signals
    from utils.coaching_notes import coaching_notes_context
    coaching_notes = coaching_notes_context()

    return {
        "week_num": week_num,
        "total_weeks": total_weeks,
        "current_phase": current_phase,
        "total_assigned": total_assigned,
        "total_completed": total_completed,
        "completion_pct": completion_pct,
        "status": status,
        "overdue_tasks": overdue_tasks,
        "recent_summaries": recent_summaries,
        "already_in_week_slugs": already_in_week_slugs,
        "ahead_slugs": ahead_slugs,
        "coaching_notes": coaching_notes,
    }


_INTENSITY_INSTRUCTIONS = {
    "light": (
        "INTENSITY: Light week. Target roughly half the normal LeetCode problem count. "
        "Prioritise reading and conceptual understanding. Skip any stretch/hard problems. "
        "Keep the overall workload manageable — it is better to finish everything than to burn out."
    ),
    "normal": (
        "INTENSITY: Normal week. Follow the phase's recommended LeetCode target and pacing."
    ),
    "intense": (
        "INTENSITY: Intense week. Target the high end of (or slightly beyond) the phase's "
        "LeetCode count. Include at least one extra system design task. Push difficulty up "
        "a notch if the phase allows. Maximise productive hours."
    ),
}


def generate_weekly_interview_prep(
    week_label: str,
    plan: dict,
    curriculum: dict,
    intensity: str = "normal",
    custom_prompt: str = "",
) -> dict:
    """
    Call Claude to generate one week of interview prep tasks.

    Returns a dict mapping day names to lists of task dicts, e.g.:
    {
      "monday": [{"type": "leetcode", "task": "#1 Two Sum", "leetcode_slug": "two-sum", "completed": false}],
      "wednesday": [{"type": "system_design", "task": "Alex Xu ch 1: Scale from zero", "leetcode_slug": null, "completed": false}]
    }
    """
    ctx = _build_context(week_label, plan, curriculum)
    phase = ctx["current_phase"]

    resources_text = "\n".join(f"  - {k}: {v}" for k, v in curriculum["resources"].items())
    phases_text = "\n".join(
        f"  Week {p['weeks_start']}-{p['weeks_end']} ({p['name']}): {p['focus']}"
        for p in curriculum["phases"]
    )
    behavioral_themes_text = "\n".join(
        f"  {i+1}. {t}" for i, t in enumerate(curriculum["behavioral_story_themes"])
    )
    topic_order_text = " → ".join(curriculum["lc_topic_order"])

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        goal=curriculum["goal"],
        resources=resources_text,
        problem_set=curriculum["problem_set"],
        phases=phases_text,
        topic_order=topic_order_text,
        behavioral_target=curriculum["behavioral_stories_target"],
        behavioral_themes=behavioral_themes_text,
        placeholder_week="ORIGINAL_WEEK",
    )

    if ctx["overdue_tasks"]:
        overdue_lines = [
            f"  - [{t['type']}] {t['task']} (originally from {t['week']}, {t['day']})"
            for t in ctx["overdue_tasks"]
        ]
        overdue_text = "\n".join(overdue_lines)
    else:
        overdue_text = "  None — all caught up!"

    if ctx["recent_summaries"]:
        recent_lines = [
            f"  - {s['week']}: {s['completed']}/{s['assigned']} tasks completed"
            for s in ctx["recent_summaries"]
        ]
        recent_text = "\n".join(recent_lines)
    else:
        recent_text = "  No prior weeks recorded yet."

    # Build existing-week context for regeneration
    existing_week = plan.get("interview_prep", {}).get(week_label, {})
    if existing_week:
        completed_lines = []
        incomplete_lines = []
        for day in _DAYS:
            for task in existing_week.get(day, []):
                entry = f"  - [{task.get('type','other')}] {task.get('task','')} ({day})"
                if task.get("completed"):
                    completed_lines.append(entry)
                else:
                    incomplete_lines.append(entry)
        existing_section = (
            "\nEXISTING WEEK DATA (this is a regeneration):\n"
            "Already completed — keep these exactly as-is, carry them into the new plan:\n"
            + ("\n".join(completed_lines) if completed_lines else "  None") + "\n"
            "Incomplete — replace or reschedule these with better tasks:\n"
            + ("\n".join(incomplete_lines) if incomplete_lines else "  None")
        )
    else:
        existing_section = ""

    intensity_instruction = _INTENSITY_INSTRUCTIONS.get(intensity, _INTENSITY_INSTRUCTIONS["normal"])
    custom_section = f"\nUSER INSTRUCTIONS:\n  {custom_prompt}" if custom_prompt else ""

    # Determine which days of this week are still in the future (including today)
    week_monday = _get_week_monday(week_label)
    today_local = date.today()
    available_days = [_DAYS[i] for i in range(7) if week_monday + timedelta(days=i) >= today_local]
    past_days = [d for d in _DAYS if d not in available_days]
    days_constraint = (
        f"\nSCHEDULING CONSTRAINT: Only assign tasks to these days (today onwards): {', '.join(available_days)}."
        + (f" Do NOT assign anything to {', '.join(past_days)} — they are already past." if past_days else "")
    )

    if ctx["already_in_week_slugs"]:
        already_section = "\n\nSLUGS ALREADY IN THIS WEEK (inserted by nightly carry-over — DO NOT add these again):\n" + \
            "\n".join(f"  - {s}" for s in sorted(ctx["already_in_week_slugs"]))
    else:
        already_section = ""

    if ctx["ahead_slugs"]:
        ahead_section = "\n\nAHEAD OF SCHEDULE — ALREADY ACCEPTED (skip these in any upcoming week's plan):\n" + \
            "\n".join(f"  - {s}" for s in sorted(ctx["ahead_slugs"]))
    else:
        ahead_section = ""

    user_message = f"""\
Generate interview prep tasks for {week_label} (Week {ctx['week_num']} of {ctx['total_weeks']}).

CURRENT PHASE: {phase['name']} (weeks {phase['weeks_start']}-{phase['weeks_end']})
Phase focus: {phase['focus']}
LeetCode difficulty: {phase['lc_difficulty']}
LeetCode target this week: {phase['lc_weekly_target']} problems
Books to draw from: {phase['books']}
System design depth: {phase['system_design_depth']}
Behavioral focus: {phase['behavioral_focus']}

{intensity_instruction}

OVERALL PROGRESS:
- Total tasks assigned across all past weeks: {ctx['total_assigned']}
- Completed: {ctx['total_completed']} ({ctx['completion_pct']}%)
- Status: {ctx['status']}

OVERDUE TASKS (incomplete from past weeks — schedule these first):
{overdue_text}

RECENT WEEK SUMMARIES:
{recent_text}
{existing_section}{already_section}{ahead_section}{days_constraint}{custom_section}

PERSISTENT COACHING NOTES (signals from the user over time — let these inform pacing and topic choices):
{ctx['coaching_notes']}

Generate a realistic, achievable week. Distribute tasks sensibly across days. \
Carry-over and completed tasks take priority. Honour any user instructions above \
even if they conflict with the default pacing guidance.\
"""

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Get the last text block (thinking blocks may precede it)
    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text")).strip()

    # Strip markdown fences if Claude wraps anyway
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    result = json.loads(raw)
    for d in past_days:
        result.pop(d, None)
    return result


_SUMMARY_SYSTEM = """\
You are an encouraging interview prep coach writing a daily briefing for a candidate.

Return ONLY valid JSON — no markdown, no explanation:
{
  "summary": "<2-3 honest, constructive sentences on overall progress — reference specific numbers>",
  "encouragement": "<1-2 sentences of genuine encouragement grounded in what they have actually done>",
  "motivation_snippet": "<1-2 sentences about why landing a role at ONE specific target company would be exciting — \
be technically specific, not generic. Rotate which company you highlight each time.>",
  "pointers": ["<specific tactical tip tailored to current phase/topic>"],
  "suggestions": ["<specific, actionable plan adjustment phrased as an action>"]
}

RULES:
- pointers: 1-3 items. Concrete, phase-appropriate study tips.
- suggestions: 2-4 items. Self-contained, specific adjustments to the plan. Each will be presented \
as a checkbox the candidate can send to their coach. Phrase as an action: "Add one extra DP problem \
this week", "Move Thursday's system design to Tuesday so you have more energy for it".
- motivation_snippet: pick ONE company from their target list. Highlight something technically exciting \
and specific about working there — a system, a team, a research direction, a product challenge.
- If on track or ahead, say so clearly. Do not invent concern.
- If significantly behind, be honest and include recovery steps in suggestions.\
"""


def generate_interview_summary(plan: dict, curriculum: dict) -> dict:
    """Generate the daily coaching summary: progress, encouragement, motivation, pointers, suggestions."""
    from utils.coaching_notes import coaching_notes_context
    from utils.interviews import interviews_context

    today = date.today()
    week_label = today.strftime("%G-W%V")
    start_date = date.fromisoformat(curriculum.get("start_date", today.isoformat()))
    start_monday = start_date - timedelta(days=start_date.weekday())
    today_monday = today - timedelta(days=today.weekday())
    week_num = max(1, (today_monday - start_monday).days // 7 + 1)
    total_weeks = curriculum.get("total_weeks", 26)

    # Compute phase
    current_phase = curriculum.get("phases", [{}])[-1]
    for phase in curriculum.get("phases", []):
        if phase.get("weeks_start", 0) <= week_num <= phase.get("weeks_end", 999):
            current_phase = phase
            break

    # Overall completion stats
    interview_prep = plan.get("interview_prep", {})
    total_assigned = total_completed = lc_completed = 0
    for wl, week_data in interview_prep.items():
        for day_tasks in week_data.values():
            for task in day_tasks:
                total_assigned += 1
                if task.get("completed"):
                    total_completed += 1
                    if task.get("type") == "leetcode":
                        lc_completed += 1

    completion_pct = round(total_completed / total_assigned * 100) if total_assigned else 100

    # Topic order progress
    topic_order = curriculum.get("lc_topic_order", [])
    topic_progress = ""
    if topic_order:
        topic_idx = min(len(topic_order) - 1, int((week_num - 1) * len(topic_order) / total_weeks))
        topic_progress = f"Current topic: {topic_order[topic_idx]} ({topic_idx + 1}/{len(topic_order)})"

    user_msg = f"""\
Candidate status:
  Week: {week_num} of {total_weeks}
  Phase: {current_phase.get('name', 'unknown')} — {current_phase.get('focus', '')[:120]}
  Overall completion: {total_completed}/{total_assigned} tasks ({completion_pct}%)
  LeetCode problems completed: {lc_completed}
  {topic_progress}
  Goal: {curriculum.get('goal', '')}
  Target companies: derived from goal above

COACHING NOTES (persistent signals):
{coaching_notes_context()}

INTERVIEW OUTCOMES (actual interviews logged):
{interviews_context()}

Write today's coaching briefing.\
"""

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=1024,
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    result = json.loads(raw)
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return result


_COACH_SYSTEM = """\
You are an interview prep coach making targeted adjustments to a candidate's weekly plan.

RULES:
1. Make ONLY the minimum changes needed to address the request. Do not restructure the whole plan.
2. Never modify or remove tasks where completed is true.
3. Preserve all task fields (type, leetcode_slug, carryover_from, etc.) when moving tasks.
4. If changes span multiple weeks (e.g. "push to next week"), include both weeks in changes.
5. If the message contains a lasting signal — a struggle, preference, or constraint that should \
shape future plans — set persistent_note to a concise one-sentence summary. Otherwise null.

Return ONLY valid JSON — no markdown fences, no explanation:
{
  "changes": {
    "<week_label>": { "<day_name>": [<full updated task list for that day>] }
  },
  "feedback": "<1-3 sentences: what you changed and why, or why no change was needed>",
  "persistent_note": "<one sentence summary of any lasting signal, or null>"
}

Include only week labels and day names that actually changed. Omit unchanged days entirely.\
"""


def coach_interview_week(
    week_label: str,
    plan: dict,
    curriculum: dict,
    user_message: str,
) -> dict:
    """
    Make targeted adjustments to the current (and optionally next) week's plan.

    Returns {"changes": {week_label: {day: [tasks]}}, "feedback": str, "persistent_note": str|None}
    """
    from utils.coaching_notes import coaching_notes_context

    next_week_monday = _get_week_monday(week_label) + timedelta(weeks=1)
    next_week_label = next_week_monday.strftime("%G-W%V")

    current_week_data = plan.get("interview_prep", {}).get(week_label, {})
    next_week_data = plan.get("interview_prep", {}).get(next_week_label, {})

    # Derive current phase for context
    start_date = date.fromisoformat(curriculum.get("start_date", date.today().isoformat()))
    monday = _get_week_monday(week_label)
    week_num = max(1, (monday - start_date).days // 7 + 1)
    current_phase = curriculum.get("phases", [{}])[-1]
    for phase in curriculum.get("phases", []):
        if phase.get("weeks_start", 0) <= week_num <= phase.get("weeks_end", 999):
            current_phase = phase
            break

    from utils.interviews import interviews_context

    user_msg = f"""\
Current week: {week_label} (Week {week_num} — phase: {current_phase.get('name', 'unknown')})

CURRENT WEEK TASKS:
{json.dumps(current_week_data, indent=2)}

NEXT WEEK ({next_week_label}) TASKS (for reference if you need to move tasks there):
{json.dumps(next_week_data, indent=2) if next_week_data else "  (no plan yet — you may add tasks here if needed)"}

PERSISTENT COACHING NOTES:
{coaching_notes_context()}

INTERVIEW OUTCOMES (actual interviews logged):
{interviews_context()}

USER MESSAGE: {user_message}
"""

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=_COACH_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return json.loads(raw)
