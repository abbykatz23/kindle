"""Manual task completion: only today's completions are persisted; old days are discarded."""
from datetime import date

from utils.state import load_state, save_state


def get_manual_completions(today: date) -> set[str]:
    """Return the set of manually-completed task names for today (empty if not today)."""
    state = load_state()
    mc = state.get("manual_completions", {})
    if mc.get("date") != today.isoformat():
        return set()
    return set(mc.get("completed", []))


def toggle_manual_completion(today: date, task_name: str) -> bool:
    """Toggle today's manual completion for `task_name`. Returns the new completion state."""
    state = load_state()
    mc = state.setdefault("manual_completions", {})
    if mc.get("date") != today.isoformat():
        mc["date"] = today.isoformat()
        mc["completed"] = []

    completed = mc["completed"]
    if task_name in completed:
        completed.remove(task_name)
        result = False
    else:
        completed.append(task_name)
        result = True

    save_state(state)
    return result
