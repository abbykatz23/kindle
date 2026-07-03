"""Scheduled jobs: Sunday-night interview prep generation + daily running compliance."""
import json
import logging
from datetime import date, timedelta

from config import Config
from utils.plan import get_week_label, load_plan, save_plan

log = logging.getLogger(__name__)

_PLAN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def run_weekly_generation() -> None:
    """Generate next week's interview prep plan if not already present."""
    if not Config.ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping weekly generation")
        return

    curriculum_path = Config.DATA_DIR / "curriculum.json"
    if not curriculum_path.exists():
        log.info("No curriculum.json — skipping weekly generation")
        return

    today = date.today()
    next_monday = today - timedelta(days=today.weekday()) + timedelta(weeks=1)
    next_week_label = get_week_label(next_monday)

    plan = load_plan()
    if plan.get("interview_prep", {}).get(next_week_label):
        log.info("Next week %s already has a plan — skipping auto-generation", next_week_label)
        return

    try:
        curriculum = json.loads(curriculum_path.read_text())
        from integrations.claude_api import generate_weekly_interview_prep
        result = generate_weekly_interview_prep(
            week_label=next_week_label,
            plan=plan,
            curriculum=curriculum,
        )
        fresh_plan = load_plan()
        fresh_plan.setdefault("interview_prep", {})[next_week_label] = result
        save_plan(fresh_plan)
        log.info("Auto-generated interview prep for %s", next_week_label)
    except Exception as exc:
        log.error("Weekly generation failed for %s: %s", next_week_label, exc)


def run_summary_generation() -> None:
    """Daily 1:30am job: generate the coaching summary panel."""
    if not Config.ANTHROPIC_API_KEY:
        return

    curriculum_path = Config.DATA_DIR / "curriculum.json"
    if not curriculum_path.exists():
        return

    try:
        curriculum = json.loads(curriculum_path.read_text())
        plan = load_plan()
        from integrations.claude_api import generate_interview_summary
        from utils.interview_summary import save_interview_summary
        summary = generate_interview_summary(plan, curriculum)
        save_interview_summary(summary)
        log.info("Interview summary generated at %s", summary.get("generated_at"))
    except Exception as exc:
        log.error("Summary generation failed: %s", exc)


def apply_actuals_to_week(active_plan: dict, week_num: int, week_data: dict, week_monday: date) -> bool:
    """Overwrite past days in week_data with actual distances from intervals.icu.

    Returns True if any day was changed. week_data is mutated in place.
    Only updates days that have a logged activity — days with no recorded run are left alone.
    """
    if not Config.INTERVALS_API_KEY:
        return False
    try:
        from integrations.intervals_api import analyze_week_compliance
        compliance = analyze_week_compliance(week_data, week_monday, active_plan.get("start_date", ""))
    except Exception as exc:
        log.error("apply_actuals_to_week failed: %s", exc)
        return False

    if not compliance.get("has_data"):
        return False

    actuals = compliance.get("actuals", {})
    plan_start_dt = date.fromisoformat(active_plan.get("start_date", str(week_monday)))
    today = date.today()
    changed = False

    for i, day_name in enumerate(_PLAN_DAYS):
        day_date = week_monday + timedelta(days=i)
        if day_date >= today or day_date < plan_start_dt:
            continue
        iso = day_date.isoformat()
        if iso not in actuals:
            continue
        actual_mi = round(actuals[iso], 2)
        day_entry = week_data.setdefault(day_name, {})
        planned_mi = float(day_entry.get("distance_miles") or 0)
        if abs(actual_mi - planned_mi) < 0.05:
            continue
        day_entry["distance_miles"] = actual_mi
        if actual_mi == 0 and day_entry.get("type") not in ("rest", None):
            day_entry["type"] = "rest"
        elif actual_mi > 0 and day_entry.get("type") == "rest":
            day_entry["type"] = "easy"
        changed = True

    return changed


def run_running_compliance_check() -> None:
    """Daily 1am job: compare yesterday's actual runs against the plan and auto-adjust."""
    if not Config.ANTHROPIC_API_KEY or not Config.INTERVALS_API_KEY:
        return

    plan = load_plan()
    running = plan.get("running", {})
    active_plan = running.get("active") if isinstance(running, dict) else None
    if not active_plan:
        return

    today = date.today()
    start_date = active_plan["start_date"]

    # Compute current plan week and its Monday
    start_dt = date.fromisoformat(start_date)
    start_monday = start_dt - timedelta(days=start_dt.weekday())
    today_monday = today - timedelta(days=today.weekday())
    week_num = max(1, ((today_monday - start_monday).days // 7) + 1)
    week_monday = start_monday + timedelta(weeks=(week_num - 1))

    # Nothing to redistribute if we're at the start of the week (Monday)
    if today == week_monday:
        return

    week_data = active_plan.get("weeks", {}).get(str(week_num), {})
    if not week_data:
        return

    # ── Retroactively update past days to match what was actually run ─────────
    retroactive_changed = apply_actuals_to_week(active_plan, week_num, week_data, week_monday)

    if retroactive_changed:
        try:
            fresh_plan = load_plan()
            if fresh_plan.get("running", {}).get("active"):
                fresh_plan["running"]["active"]["weeks"][str(week_num)] = week_data
                save_plan(fresh_plan)
                log.info("Running compliance: retroactively updated past days for week %s", week_num)
        except Exception as exc:
            log.error("Running compliance retroactive update failed: %s", exc)

    if not compliance.get("missed_runs") and not compliance.get("short_runs"):
        return

    # Check there are remaining days to redistribute to
    remaining = [
        day for i, day in enumerate(_PLAN_DAYS)
        if week_monday + timedelta(days=i) >= today
    ]
    if not remaining:
        log.info("Running compliance: gaps found but no remaining days this week — skipping")
        return

    summary = compliance.get("summary_text", "")
    log.info("Running compliance: gaps detected, auto-adjusting week %s", week_num)

    try:
        from integrations.running_claude_api import edit_weekly_running_plan
        result = edit_weekly_running_plan(
            week_num=week_num,
            active_plan=active_plan,
            custom_prompt=summary,
        )
        fresh_plan = load_plan()
        if fresh_plan.get("running", {}).get("active"):
            fresh_plan["running"]["active"]["weeks"][str(week_num)] = result
            save_plan(fresh_plan)
            log.info("Running compliance: week %s auto-adjusted", week_num)
    except Exception as exc:
        log.error("Running compliance auto-adjust failed: %s", exc)
