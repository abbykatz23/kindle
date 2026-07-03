"""Load/save persistent coaching notes for the interview prep coach."""
import json
from datetime import datetime

from config import Config


def load_coaching_notes() -> list[dict]:
    if Config.COACHING_NOTES_FILE.exists():
        return json.loads(Config.COACHING_NOTES_FILE.read_text())
    return []


def save_coaching_note(summary: str, original_message: str) -> None:
    notes = load_coaching_notes()
    notes.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "original": original_message,
    })
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.COACHING_NOTES_FILE.write_text(json.dumps(notes, indent=2))


def coaching_notes_context(max_entries: int = 15) -> str:
    """Return a formatted string of recent coaching notes for inclusion in prompts."""
    notes = load_coaching_notes()
    if not notes:
        return "None"
    recent = notes[-max_entries:]
    return "\n".join(f"  [{n['timestamp'][:10]}] {n['summary']}" for n in recent)
