"""Persist the current Kindle display view across process restarts."""
import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent / "data" / "kindle_view.json"
VALID_VIEWS = {"dashboard", "running", "interview", "birthdays"}


def get_view() -> str:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text()).get("view", "dashboard")
        except Exception:
            pass
    return "dashboard"


def set_view(view: str) -> None:
    if view not in VALID_VIEWS:
        raise ValueError(f"Unknown view: {view!r}")
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"view": view}))
