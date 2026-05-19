"""
Runs every 30 minutes via cron.
Checks whether Strava or LeetCode state has changed since the last poll,
and triggers a full re-render + push if it has.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from config import Config
from integrations.leetcode import get_todays_submission
from integrations.strava import get_todays_run

_PROJECT_ROOT = Path(__file__).parent.parent


def _load_state() -> dict:
    if Config.STATE_FILE.exists():
        return json.loads(Config.STATE_FILE.read_text())
    return {"strava": {}, "leetcode": {}}


def _save_state(state: dict) -> None:
    state["last_updated"] = datetime.now().isoformat()
    Config.STATE_FILE.write_text(json.dumps(state, indent=2))


def check_and_refresh() -> bool:
    """Return True if state changed and a refresh was triggered."""
    state = _load_state()
    changed = False

    run = get_todays_run()
    run_id = run["id"] if run else None
    if run_id != state.get("strava", {}).get("last_activity_id"):
        state.setdefault("strava", {})["last_activity_id"] = run_id
        state["strava"]["last_activity_date"] = run["date"] if run else None
        changed = True

    sub = get_todays_submission(Config.LEETCODE_USERNAME)
    sub_id = str(sub["id"]) if sub else None
    if sub_id != state.get("leetcode", {}).get("last_submission_id"):
        state.setdefault("leetcode", {})["last_submission_id"] = sub_id
        state["leetcode"]["last_problem_slug"] = sub["titleSlug"] if sub else None
        changed = True

    if changed:
        _save_state(state)
        import subprocess
        subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "main.py")],
            check=True,
            cwd=str(_PROJECT_ROOT),
        )

    return changed


if __name__ == "__main__":
    refreshed = check_and_refresh()
    print("Refreshed." if refreshed else "No change.")
