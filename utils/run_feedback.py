"""Cache one AI coaching note per calendar day in data/run_feedback.json."""
import json
import sys
from datetime import date
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "data" / "run_feedback.json"


def load_todays_feedback(today: date) -> str | None:
    """Return cached feedback for today, or None if not yet generated."""
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text())
        if data.get("date") == today.isoformat():
            return data.get("feedback") or None
    except Exception:
        pass
    return None


def save_feedback(today: date, feedback: str) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps({"date": today.isoformat(), "feedback": feedback}))


def get_or_generate_feedback(
    today: date,
    planned_run: dict | None,
    week_plan: dict,
    plan_meta: dict,
) -> str | None:
    """Return today's cached feedback, generating it on first call if not yet stored."""
    cached = load_todays_feedback(today)
    if cached:
        return cached

    if not planned_run:
        return None

    try:
        from integrations.intervals_api import get_todays_run_detail
        actual_run = get_todays_run_detail()
        if not actual_run:
            return None

        from integrations.run_feedback_claude import generate_run_feedback
        feedback = generate_run_feedback(planned_run, actual_run, week_plan, plan_meta, today)
        save_feedback(today, feedback)
        return feedback
    except Exception as e:
        print(f"run feedback generation failed: {e}", file=sys.stderr)
        return None
