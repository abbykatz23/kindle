"""Read/write helpers for state.json (runtime state — last seen IDs, manual completions)."""
import json
from datetime import datetime

from config import Config


def load_state() -> dict:
    if Config.STATE_FILE.exists():
        return json.loads(Config.STATE_FILE.read_text())
    return {"manual_completions": {}}


def save_state(state: dict) -> None:
    state["last_updated"] = datetime.now().isoformat()
    Config.STATE_FILE.write_text(json.dumps(state, indent=2))
