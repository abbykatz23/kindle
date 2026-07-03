"""Claude-powered interview prep curriculum generation."""
import json
from datetime import date

import anthropic

from config import Config

_CURRICULUM_SCHEMA = """\
{
  "start_date": "YYYY-MM-DD",
  "target_date": "YYYY-MM-DD",
  "total_weeks": <integer>,
  "goal": "<one sentence describing the overall prep goal>",
  "resources": {
    "<SHORTKEY>": "<title, author, brief note on what it covers and why it is relevant>"
  },
  "problem_set": "<one sentence on the LeetCode/problem-solving approach>",
  "phases": [
    {
      "name": "<phase name>",
      "weeks_start": <int>,
      "weeks_end": <int>,
      "focus": "<paragraph describing what this phase covers>",
      "lc_difficulty": "<e.g. 'easy and medium' or 'medium and hard' or 'hard'>",
      "lc_weekly_target": <int>,
      "books": "<which resources and sections to use this phase>",
      "system_design_depth": "<light | medium | deep | mock interview mode>",
      "behavioral_focus": "<what to do for behavioral prep this phase>"
    }
  ],
  "lc_topic_order": ["<topic 1>", "<topic 2>", "..."],
  "behavioral_stories_target": <int>,
  "behavioral_story_themes": ["<theme 1>", "..."]
}"""

_QUESTIONS_SYSTEM = """\
You are a technical interview prep coach. The candidate has given you their basic information. \
Ask 3–5 short, targeted follow-up questions that will meaningfully improve the curriculum you write for them.

Focus on what matters most for personalisation:
- Which specific topics or data structures they find hardest
- How much system design experience they have vs. algorithms
- Whether they have a specific interview date or just a rough window
- Any constraints (time zone, part-time job, health, travel weeks to exclude)
- Whether they have previously attempted interviews at these companies and what feedback they received

Format: numbered list, one question per line. No preamble, no explanation."""

_CURRICULUM_SYSTEM = """\
You are a technical interview prep coach building a personalised multi-week study curriculum.

Return ONLY valid JSON matching this exact schema — no markdown fences, no explanation:
{schema}

RULES:
- start_date is today: {today}
- Derive target_date and total_weeks from the user's stated timeline
- Design 3–4 phases with a clear arc: foundation → build → depth → polish
- Tailor resources to the target role (ML roles need ML system design; backend SWE needs distributed systems depth; etc.)
- lc_topic_order: order topics from fundamentals to advanced — this sequence is followed across all weeks
- behavioral_story_themes: exactly 8 specific STAR story prompts, tailored to the target company culture
- All field names and value types must exactly match the schema"""

_QUESTIONS_USER_TEMPLATE = """\
Intake information:
{intake}"""

_CURRICULUM_USER_TEMPLATE = """\
Generate a curriculum for this candidate:
{intake}
{qa_context}"""


def generate_curriculum_questions(intake: dict) -> str:
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    intake_text = "\n".join(f"  {k}: {v}" for k, v in intake.items() if v)
    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=512,
        system=_QUESTIONS_SYSTEM,
        messages=[{"role": "user", "content": _QUESTIONS_USER_TEMPLATE.format(intake=intake_text)}],
    )
    return message.content[0].text.strip()


def generate_curriculum(intake: dict, progress_cb=None) -> dict:
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    if progress_cb:
        progress_cb("Designing your curriculum...")

    intake_text = "\n".join(f"  {k}: {v}" for k, v in intake.items() if k != "qa_context" and v)
    qa_section = ""
    if intake.get("qa_context"):
        qa_section = f"\nADDITIONAL CONTEXT (follow-up Q&A):\n{intake['qa_context']}"

    from utils.coaching_notes import coaching_notes_context
    notes = coaching_notes_context()
    notes_section = f"\nPERSISTENT COACHING NOTES (factor these into the plan design):\n{notes}" if notes != "None" else ""

    system = _CURRICULUM_SYSTEM.format(schema=_CURRICULUM_SCHEMA, today=date.today().isoformat())
    user_message = _CURRICULUM_USER_TEMPLATE.format(intake=intake_text, qa_context=qa_section) + notes_section

    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    if progress_cb:
        progress_cb("Parsing curriculum...")

    raw = next(b.text for b in reversed(message.content) if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    curriculum = json.loads(raw)

    required_fields = ["start_date", "target_date", "total_weeks", "goal", "phases", "lc_topic_order"]
    for field in required_fields:
        if field not in curriculum:
            raise ValueError(f"Curriculum response missing required field: {field}")

    return curriculum
