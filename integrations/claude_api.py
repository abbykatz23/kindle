import json

import anthropic

from config import Config

_SYSTEM_PROMPT = (
    "You are a technical interview coach generating a structured weekly study plan. "
    "Return only valid JSON with no markdown fences or extra text. "
    "The JSON must map lowercase day names (monday–sunday) to task objects, each with: "
    "type (one of: leetcode, system_design, behavioral, reading), "
    "task (short description), "
    "leetcode_slug (problem slug if type is leetcode, else null), "
    "notes (optional extra context, can be empty string)."
)


def generate_weekly_interview_prep(
    week_label: str,
    monthly_skeleton: str,
    existing_weeks: list[str],
) -> dict:
    """
    Call Claude to generate one week of interview prep tasks.

    Returns a dict mapping day names to task objects:
    {"monday": {"type": "leetcode", "task": "...", "leetcode_slug": "...", "notes": ""}, ...}
    """
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    user_prompt = (
        f"Generate interview prep tasks for week {week_label}.\n\n"
        f"Monthly prep skeleton:\n{monthly_skeleton}\n\n"
        f"Weeks already covered: {', '.join(existing_weeks) if existing_weeks else 'none'}\n\n"
        "Return a JSON object covering all 7 days of this week."
    )

    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return json.loads(message.content[0].text)
