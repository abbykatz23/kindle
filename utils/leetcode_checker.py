"""Daily LeetCode completion check — carries over unfinished problems and detects ahead-of-schedule work."""
import logging
from datetime import date, timedelta

from config import Config
from integrations.leetcode import get_recent_accepted_submissions
from utils.plan import get_tasks_for_date, get_week_label, load_plan, save_plan
from utils.state import load_state, save_state

log = logging.getLogger(__name__)

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _all_future_lc_slugs(plan: dict, from_date: date) -> set[str]:
    """Return the set of all LC slugs scheduled on or after from_date in the plan."""
    slugs: set[str] = set()
    interview_prep = plan.get("interview_prep", {})
    for week_label, week_data in interview_prep.items():
        try:
            year, wnum = week_label.split("-W")
            monday = date.fromisocalendar(int(year), int(wnum), 1)
        except (ValueError, AttributeError):
            continue
        for i, day_name in enumerate(_DAYS):
            day_date = monday + timedelta(days=i)
            if day_date < from_date:
                continue
            for task in week_data.get(day_name, []):
                slug = task.get("leetcode_slug")
                if slug and task.get("type") == "leetcode":
                    slugs.add(slug)
    return slugs


def run_carryover_check() -> None:
    """1am daily job: carry over yesterday's incomplete LC tasks and detect ahead-of-schedule work."""
    if not Config.LEETCODE_USERNAME:
        log.warning("LEETCODE_USERNAME not set — skipping carryover check")
        return

    today = date.today()
    yesterday = today - timedelta(days=1)

    try:
        submissions = get_recent_accepted_submissions(Config.LEETCODE_USERNAME, limit=50)
        accepted_slugs = {s["titleSlug"] for s in submissions}
    except Exception as exc:
        log.error("LeetCode API error during carryover check: %s", exc)
        return

    plan = load_plan()
    state = load_state()

    # ── Detect ahead-of-schedule completions ─────────────────────────────
    tomorrow = today + timedelta(days=1)
    future_slugs = _all_future_lc_slugs(plan, tomorrow)
    state["leetcode_ahead"] = sorted(accepted_slugs & future_slugs)

    # ── Carryover: yesterday's incomplete LC tasks ────────────────────────
    yesterday_tasks = get_tasks_for_date(yesterday)
    lc_tasks = [
        t for t in yesterday_tasks
        if t.get("type") == "leetcode" and t.get("leetcode_slug")
    ]

    if lc_tasks:
        today_day = today.strftime("%A").lower()
        today_week = get_week_label(today)

        # All slugs already scheduled from today onwards — don't duplicate
        today_onward_slugs = _all_future_lc_slugs(plan, today)

        carryovers = state.setdefault("leetcode_carryovers", [])
        already_carried_today = {c["slug"] for c in carryovers if c.get("carried_to") == today.isoformat()}

        added = []
        for task in lc_tasks:
            slug = task["leetcode_slug"]
            if slug in accepted_slugs:
                continue
            if slug in today_onward_slugs or slug in already_carried_today:
                continue

            new_task = {**task, "carryover_from": yesterday.isoformat(), "completed": False}
            (
                plan.setdefault("interview_prep", {})
                    .setdefault(today_week, {})
                    .setdefault(today_day, [])
                    .append(new_task)
            )
            carryovers.append({
                "slug": slug,
                "task": task.get("task", slug),
                "originally_assigned": task.get("carryover_from", yesterday.isoformat()),
                "carried_to": today.isoformat(),
            })
            added.append(slug)

        if added:
            cutoff = (today - timedelta(days=14)).isoformat()
            state["leetcode_carryovers"] = [
                c for c in carryovers if c.get("carried_to", "") >= cutoff
            ]
            save_plan(plan)
            log.info("Carried over %d LeetCode task(s): %s", len(added), added)

    save_state(state)
