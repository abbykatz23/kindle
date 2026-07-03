"""Load/save persistent running coaching notes."""
import json
from datetime import datetime
from config import Config


def load_running_coaching_notes() -> list[dict]:
    if Config.RUNNING_COACHING_NOTES_FILE.exists():
        try:
            return json.loads(Config.RUNNING_COACHING_NOTES_FILE.read_text())
        except Exception:
            return []
    return []


def add_running_coaching_note(summary: str, original: str = "") -> None:
    notes = load_running_coaching_notes()
    notes.insert(0, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "original": original,
    })
    _save(notes[:20])


def running_coaching_notes_context(max_entries: int = 6) -> str:
    notes = load_running_coaching_notes()
    if not notes:
        return "None"
    return "\n".join(
        f"  [{n['timestamp'][:10]}] {n['summary']}" for n in notes[:max_entries]
    )


def _save(notes: list[dict]) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.RUNNING_COACHING_NOTES_FILE.write_text(json.dumps(notes, indent=2))
