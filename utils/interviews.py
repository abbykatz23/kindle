"""Load/save interview outcome log."""
import json
import uuid
from config import Config


def load_interviews() -> list[dict]:
    if Config.INTERVIEWS_FILE.exists():
        try:
            return json.loads(Config.INTERVIEWS_FILE.read_text())
        except Exception:
            return []
    return []


def add_interview(entry: dict) -> dict:
    interviews = load_interviews()
    entry = {**entry, "id": uuid.uuid4().hex[:8]}
    interviews.insert(0, entry)
    _save(interviews)
    return entry


def delete_interview(interview_id: str) -> bool:
    interviews = load_interviews()
    before = len(interviews)
    interviews = [i for i in interviews if i.get("id") != interview_id]
    if len(interviews) < before:
        _save(interviews)
        return True
    return False


def interviews_context(max_entries: int = 10) -> str:
    """Format recent interview outcomes for inclusion in prompts."""
    interviews = load_interviews()
    if not interviews:
        return "None"
    recent = interviews[:max_entries]
    lines = []
    for iv in recent:
        line = f"  [{iv.get('date', '?')}] {iv.get('company', '?')} — {iv.get('round_type', '?')}: {iv.get('result', '?')}"
        if iv.get("notes"):
            line += f" · {iv['notes']}"
        lines.append(line)
    return "\n".join(lines)


def _save(interviews: list[dict]) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.INTERVIEWS_FILE.write_text(json.dumps(interviews, indent=2))
