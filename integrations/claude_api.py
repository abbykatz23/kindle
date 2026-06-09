import json
from datetime import date

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
{existing_section}{custom_section}

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

    return json.loads(raw)
