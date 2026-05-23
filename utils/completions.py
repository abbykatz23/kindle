"""Per-date manual task completions. Old weeks are pruned on every write."""
from datetime import date, timedelta

from utils.state import load_state, save_state


def _week_start(d: date) -> date:
    """Monday of the week containing `d`."""
    return d - timedelta(days=d.weekday())


def get_manual_completions(d: date) -> set[str]:
    """Return the set of manually-completed task names for the given date."""
    state = load_state()
    by_date = state.get("manual_completions", {})
    return set(by_date.get(d.isoformat(), []))


def toggle_manual_completion(d: date, task_name: str) -> bool:
    """Toggle a manual completion for the given date. Returns the new state."""
    state = load_state()
    by_date = state.setdefault("manual_completions", {})

    today_week_start = _week_start(date.today())
    by_date = {
        k: v for k, v in by_date.items()
        if date.fromisoformat(k) >= today_week_start
    }
    state["manual_completions"] = by_date

    key = d.isoformat()
    completed = by_date.setdefault(key, [])
    if task_name in completed:
        completed.remove(task_name)
        result = False
    else:
        completed.append(task_name)
        result = True

    save_state(state)
    return result
