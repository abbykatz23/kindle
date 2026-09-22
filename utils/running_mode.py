"""Persist which mode the Kindle's RUNNING section is in: the training plan, or the last run."""
import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent / "data" / "running_mode.json"
MODE_PLAN = "plan"
MODE_LAST_RUN = "last_run"
VALID_MODES = {MODE_PLAN, MODE_LAST_RUN}


def get_running_mode() -> str:
    if _STATE_FILE.exists():
        try:
            mode = json.loads(_STATE_FILE.read_text()).get("mode")
            if mode in VALID_MODES:
                return mode
        except Exception:
            pass
    return MODE_PLAN


def set_running_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown running mode: {mode!r}")
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"mode": mode}))
