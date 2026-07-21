"""Persist the current Kindle display view across process restarts."""
import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent / "data" / "kindle_view.json"
VALID_VIEWS = {"dashboard", "running", "learning", "birthdays", "running_day"}


def _read() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def get_view() -> str:
    return _read().get("view", "dashboard")


def get_selected_date() -> str | None:
    return _read().get("selected_date")


def get_pending_minutes() -> int | None:
    """The minute value 'armed' via the dashboard's shared 5/15 buttons, if any."""
    return _read().get("pending_minutes")


def set_pending_minutes(minutes: int | None) -> None:
    """Merge-write so this survives independently of set_view()'s full-state reset."""
    state = _read()
    if minutes is None:
        state.pop("pending_minutes", None)
    else:
        state["pending_minutes"] = minutes
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state))


def set_view(view: str, selected_date: str | None = None) -> None:
    if view not in VALID_VIEWS:
        raise ValueError(f"Unknown view: {view!r}")
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state: dict = {"view": view}
    if selected_date is not None:
        state["selected_date"] = selected_date
    _STATE_FILE.write_text(json.dumps(state))
