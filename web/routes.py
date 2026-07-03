import json
import threading
from datetime import date, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from config import Config
from integrations.leetcode import get_problem_by_number
from utils import jobs as job_store
from utils.plan import get_week_label, get_week_monday, get_week_task_lists, load_plan, load_birthdays, save_birthdays
from utils.tap_handler import handle_tap

bp = Blueprint("main", __name__)

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WORKOUT_TYPES = ["easy", "workout", "long", "rest", "race", "other"]

MONTH_DAY_LIMITS = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def _normalize_birthday_date(month_str: str, day_str: str, date_str: str | None = None) -> str:
    if month_str and day_str:
        month = int(month_str)
        day = int(day_str)
    elif date_str:
        parts = date_str.split("-")
        if len(parts) == 3:
            _, month_s, day_s = parts
        elif len(parts) == 2:
            month_s, day_s = parts
        else:
            raise ValueError()
        month = int(month_s)
        day = int(day_s)
    else:
        raise ValueError()
    if not (1 <= month <= 12):
        raise ValueError()
    max_day = MONTH_DAY_LIMITS.get(month)
    if not max_day or not (1 <= day <= max_day):
        raise ValueError()
    return f"{month:02d}-{day:02d}"


def _get_plan_week_monday(start_date_str: str, week_num: int) -> date:
    start = date.fromisoformat(start_date_str)
    start_monday = start - timedelta(days=start.weekday())
    return start_monday + timedelta(weeks=(week_num - 1))


def _get_current_plan_week(start_date_str: str, today: date) -> int:
    start = date.fromisoformat(start_date_str)
    start_monday = start - timedelta(days=start.weekday())
    today_monday = today - timedelta(days=today.weekday())
    delta = (today_monday - start_monday).days // 7
    return max(1, delta + 1)


def _save_plan(plan: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.PLAN_FILE.write_text(json.dumps(plan, indent=2))


def _load_sorted_birthdays() -> list[dict]:
    return sorted(load_birthdays(), key=lambda b: b.get("date", ""))


def _get_next_birthday(birthdays: list[dict], today: date) -> dict | None:
    best: dict | None = None
    best_days: int | None = None
    for b in birthdays:
        try:
            month, day = map(int, b["date"].split("-"))
        except (ValueError, KeyError):
            continue
        for year_offset in [0, 1]:
            try:
                bday = date(today.year + year_offset, month, day)
            except ValueError:
                bday = date(today.year + year_offset, 3, 1)  # Feb 29 fallback
            days_until = (bday - today).days
            if days_until >= 0:
                if best_days is None or days_until < best_days:
                    best_days = days_until
                    best = {"name": b.get("name", ""), "days_until": days_until}
                break
    return best


def _interview_week_stats(week_data: dict) -> dict:
    stats: dict = {"total": 0, "done": 0, "by_type": {}}
    for day_tasks in week_data.values():
        for task in day_tasks:
            stats["total"] += 1
            if task.get("completed"):
                stats["done"] += 1
            t = task.get("type", "other")
            stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
    return stats


def _interview_redirect(week_label: str):
    ref = request.referrer or ""
    if "/interview/week/" in ref:
        return redirect(url_for("main.interview_week", week_label=week_label))
    return redirect(url_for("main.index", tab="interview"))


def _preserve_notes_actual(new_week: dict, existing_week: dict) -> dict:
    """Copy notes_actual from existing days into new week data (so Claude edits don't wipe them)."""
    for day, existing_day in existing_week.items():
        if existing_day.get("notes_actual") and day in new_week:
            new_week[day]["notes_actual"] = existing_day["notes_actual"]
    return new_week


def _running_generate_thread(job_id: str, week_num: int, custom_prompt: str) -> None:
    try:
        from integrations.running_claude_api import edit_weekly_running_plan
        plan = load_plan()
        running = plan.get("running", {})
        active_plan = running.get("active") if isinstance(running, dict) else None
        if not active_plan:
            raise ValueError("No active running plan found.")
        result = edit_weekly_running_plan(
            week_num=week_num,
            active_plan=active_plan,
            custom_prompt=custom_prompt,
        )
        fresh_plan = load_plan()
        if fresh_plan.get("running", {}).get("active"):
            existing = fresh_plan["running"]["active"]["weeks"].get(str(week_num), {})
            fresh_plan["running"]["active"]["weeks"][str(week_num)] = _preserve_notes_actual(result, existing)
            _save_plan(fresh_plan)
        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _running_coach_thread(job_id: str, user_message: str) -> None:
    try:
        from integrations.running_claude_api import coach_running_plan
        from utils.race_results import race_results_context
        from utils.running_coaching_notes import running_coaching_notes_context, add_running_coaching_note

        plan = load_plan()
        running = plan.get("running", {})
        active_plan = running.get("active") if isinstance(running, dict) else None
        if not active_plan:
            raise ValueError("No active running plan found.")

        today = date.today()
        start_date = active_plan["start_date"]
        current_week_num = _get_current_plan_week(start_date, today)

        result = coach_running_plan(
            active_plan=active_plan,
            current_week_num=current_week_num,
            user_message=user_message,
            race_results_ctx=race_results_context(),
            coaching_notes_ctx=running_coaching_notes_context(),
        )

        changes = result.get("changes", {})
        if changes:
            fresh_plan = load_plan()
            active = fresh_plan.get("running", {}).get("active")
            if active:
                for wnum_str, week_changes in changes.items():
                    existing = active.get("weeks", {}).get(wnum_str, {})
                    merged = {**existing}
                    for day, day_data in week_changes.items():
                        if not isinstance(day_data, dict):
                            continue
                        existing_day = existing.get(day, {})
                        if isinstance(existing_day, dict) and existing_day.get("notes_actual"):
                            day_data = {**day_data, "notes_actual": existing_day["notes_actual"]}
                        merged[day] = day_data
                    active.setdefault("weeks", {})[wnum_str] = merged
                _save_plan(fresh_plan)

        if result.get("persistent_note"):
            add_running_coaching_note(result["persistent_note"], user_message)

        if result.get("feedback"):
            job_store.mark_progress(job_id, result["feedback"])
        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _running_generate_full_thread(job_id: str, intake: dict) -> None:
    try:
        from integrations.running_claude_api import generate_full_running_plan

        def _progress(msg: str):
            job_store.mark_progress(job_id, msg)

        weeks_data = generate_full_running_plan(intake, progress_cb=_progress)

        today = date.today()
        try:
            race_miles_f = float(intake.get("race_miles") or 0)
            if intake.get("race_distance_unit") == "km":
                race_miles_f = round(race_miles_f * 0.621371, 1)
        except (TypeError, ValueError):
            race_miles_f = 0

        new_active = {
            "id": f"plan_{today.strftime('%Y%m%d')}",
            "created_at": today.isoformat(),
            "start_date": intake.get("start_date", today.isoformat()),
            "race_date": intake.get("race_date", ""),
            "race_name": intake.get("race_name", ""),
            "race_miles": race_miles_f,
            "days_per_week": int(intake.get("days_per_week") or 4),
            "current_weekly_mileage": float(intake.get("current_weekly_mileage") or 0),
            "notes": intake.get("notes", ""),
            "weeks": weeks_data,
        }

        fresh_plan = load_plan()
        running = fresh_plan.setdefault("running", {})
        if not isinstance(running, dict) or "active" not in running:
            running = {"active": None, "archived": []}
            fresh_plan["running"] = running

        if running.get("active"):
            existing = running["active"]
            existing["archived_at"] = today.isoformat()
            running.setdefault("archived", []).insert(0, existing)

        running["active"] = new_active
        _save_plan(fresh_plan)

        # Immediately backfill week 1 past days with actual run data
        try:
            from utils.weekly_generator import apply_actuals_to_week
            start_dt = date.fromisoformat(new_active["start_date"])
            week1_monday = start_dt - timedelta(days=start_dt.weekday())
            week1_data = new_active["weeks"].get("1", {})
            if apply_actuals_to_week(new_active, 1, week1_data, week1_monday):
                fresh_plan2 = load_plan()
                if fresh_plan2.get("running", {}).get("active"):
                    fresh_plan2["running"]["active"]["weeks"]["1"] = week1_data
                    _save_plan(fresh_plan2)
        except Exception:
            pass  # non-fatal — nightly job will catch it

        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _coach_thread(job_id: str, week_label: str, user_message: str) -> None:
    try:
        from integrations.claude_api import coach_interview_week
        plan = load_plan()
        curriculum_path = Config.DATA_DIR / "curriculum.json"
        curriculum = json.loads(curriculum_path.read_text()) if curriculum_path.exists() else {}

        result = coach_interview_week(
            week_label=week_label,
            plan=plan,
            curriculum=curriculum,
            user_message=user_message,
        )

        # Apply changes: merge day-by-day, never replace whole weeks
        changes = result.get("changes", {})
        if changes:
            fresh_plan = load_plan()
            interview = fresh_plan.setdefault("interview_prep", {})
            for wl, week_changes in changes.items():
                week_data = interview.setdefault(wl, {})
                for day, tasks in week_changes.items():
                    week_data[day] = tasks
            _save_plan(fresh_plan)

        # Persist coaching note if Claude extracted one
        note = result.get("persistent_note")
        if note:
            from utils.coaching_notes import save_coaching_note
            save_coaching_note(note, user_message)

        job_store.mark_done(job_id, extra={"feedback": result.get("feedback", "")})
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _curriculum_generate_thread(job_id: str, intake: dict) -> None:
    try:
        from integrations.curriculum_claude_api import generate_curriculum

        def _progress(msg: str):
            job_store.mark_progress(job_id, msg)

        curriculum = generate_curriculum(intake, progress_cb=_progress)

        # Always anchor start_date to this week's Monday so week counter = 1
        today = date.today()
        this_monday = (today - timedelta(days=today.weekday())).isoformat()
        curriculum["start_date"] = this_monday

        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (Config.DATA_DIR / "curriculum.json").write_text(json.dumps(curriculum, indent=2))

        # Clear stale interview_prep data — regeneration is a fresh start
        fresh_plan = load_plan()
        fresh_plan["interview_prep"] = {}
        _save_plan(fresh_plan)

        # Clear stale coaching summary so it regenerates from the new curriculum
        if Config.INTERVIEW_SUMMARY_FILE.exists():
            Config.INTERVIEW_SUMMARY_FILE.unlink()

        # Generate this week's plan
        _progress("Generating this week's plan...")
        from utils.plan import get_week_label as _gwl
        week_label = _gwl(today)
        plan = load_plan()
        from integrations.claude_api import generate_weekly_interview_prep
        result = generate_weekly_interview_prep(
            week_label=week_label,
            plan=plan,
            curriculum=curriculum,
        )
        fresh_plan = load_plan()
        fresh_plan.setdefault("interview_prep", {})[week_label] = result
        _save_plan(fresh_plan)

        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _claude_generate_thread(job_id: str, week_label: str, curriculum: dict, intensity: str = "normal", custom_prompt: str = "") -> None:
    try:
        from integrations.claude_api import generate_weekly_interview_prep
        plan = load_plan()
        result = generate_weekly_interview_prep(
            week_label=week_label,
            plan=plan,
            curriculum=curriculum,
            intensity=intensity,
            custom_prompt=custom_prompt,
        )
        fresh_plan = load_plan()
        fresh_plan.setdefault("interview_prep", {})[week_label] = result
        _save_plan(fresh_plan)
        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


@bp.route("/")
def index():
    today = date.today()
    current_week = get_week_label(today)
    plan = load_plan()
    birthdays = _load_sorted_birthdays()
    leetcode_tasks, other_tasks = get_week_task_lists(today)
    for t in leetcode_tasks + other_tasks:
        task_date = date.fromisoformat(t["date"])
        t["day_name"] = task_date.strftime("%A")
        t["formatted_date"] = task_date.strftime("%b %d").lstrip("0")

    default_tab = (request.args.get("tab") or "interview").lower()

    # Interview prep
    interview_past_weeks = sorted(
        [w for w in plan.get("interview_prep", {}) if w < current_week],
        reverse=True,
    )

    current_interview = plan.get("interview_prep", {}).get(current_week, {})

    # Attach date + completion status to current week's tasks (in-memory only)
    from utils.completions import get_manual_completions
    _comp_cache: dict[str, set] = {}
    today_monday = today - timedelta(days=today.weekday())
    for _i, _day in enumerate(DAYS):
        _day_date = today_monday + timedelta(days=_i)
        _iso = _day_date.isoformat()
        if _iso not in _comp_cache:
            _comp_cache[_iso] = get_manual_completions(_day_date)
        for _task in current_interview.get(_day, []):
            _task["date"] = _iso
            _task["completed"] = _task.get("task", "") in _comp_cache[_iso]

    interview_week_stats = {
        w: _interview_week_stats(data)
        for w, data in plan.get("interview_prep", {}).items()
    }

    carryover_by_day: dict[str, int] = {}
    total_carryovers = 0
    for _day in DAYS:
        count = sum(1 for t in current_interview.get(_day, []) if t.get("carryover_from"))
        carryover_by_day[_day] = count
        total_carryovers += count

    # Running plan — new data model: {active: {...}, archived: [...]}
    running_section = plan.get("running", {})
    if isinstance(running_section, dict) and "active" in running_section:
        active_plan = running_section.get("active")
        archived_plans = running_section.get("archived", [])
    else:
        active_plan = None
        archived_plans = []

    if active_plan:
        start_date = active_plan["start_date"]
        total_plan_weeks = len(active_plan.get("weeks", {}))
        current_plan_week = _get_current_plan_week(start_date, today)
        current_plan_week = min(max(1, current_plan_week), total_plan_weeks) if total_plan_weeks else 1
        race_date_str = active_plan.get("race_date", "")
        race_name = active_plan.get("race_name", "")
        past_plan_weeks = list(range(1, current_plan_week))
        future_plan_weeks = list(range(current_plan_week + 1, total_plan_weeks + 1))
        week_dates = {}
        for wnum in range(1, total_plan_weeks + 1):
            mon = _get_plan_week_monday(start_date, wnum)
            week_dates[wnum] = {"monday": mon, "sunday": mon + timedelta(days=6)}
    else:
        total_plan_weeks = 0
        current_plan_week = None
        race_date_str = ""
        race_name = ""
        past_plan_weeks = []
        future_plan_weeks = []
        week_dates = {}

    next_birthday = _get_next_birthday(birthdays, today)

    curriculum_path = Config.DATA_DIR / "curriculum.json"
    curriculum = json.loads(curriculum_path.read_text()) if curriculum_path.exists() else None

    # Topic coverage
    current_topic = topic_idx = topics_total = lc_completed = 0
    current_topic_name = None
    if curriculum:
        topic_order = curriculum.get("lc_topic_order", [])
        total_weeks = curriculum.get("total_weeks", 1)
        start_dt = date.fromisoformat(curriculum.get("start_date", today.isoformat()))
        start_mon = start_dt - timedelta(days=start_dt.weekday())
        today_mon = today - timedelta(days=today.weekday())
        curr_week_num = max(1, (today_mon - start_mon).days // 7 + 1)
        if topic_order:
            topic_idx = min(len(topic_order) - 1, int((curr_week_num - 1) * len(topic_order) / total_weeks))
            current_topic_name = topic_order[topic_idx]
            topics_total = len(topic_order)
        lc_completed = sum(
            1 for week_data in plan.get("interview_prep", {}).values()
            for day_tasks in week_data.values()
            for task in day_tasks
            if task.get("type") == "leetcode" and task.get("completed")
        )

    from utils.interview_summary import load_interview_summary
    from utils.interviews import load_interviews
    from utils.race_results import load_race_results
    interview_summary = load_interview_summary()
    interviews = load_interviews()
    race_results = load_race_results()

    return render_template(
        "index.html",
        current_week=current_week,
        interview_past_weeks=interview_past_weeks,
        interview_week_stats=interview_week_stats,
        plan=plan,
        birthdays=birthdays,
        leetcode_tasks=leetcode_tasks,
        other_tasks=other_tasks,
        default_tab=default_tab,
        days=DAYS,
        workout_types=WORKOUT_TYPES,
        today=today,
        timedelta=timedelta,
        get_week_monday=get_week_monday,
        active_plan=active_plan,
        archived_plans=archived_plans,
        current_plan_week=current_plan_week,
        total_plan_weeks=total_plan_weeks,
        past_plan_weeks=past_plan_weeks,
        future_plan_weeks=future_plan_weeks,
        week_dates=week_dates,
        race_date_str=race_date_str,
        race_name=race_name,
        next_birthday=next_birthday,
        carryover_by_day=carryover_by_day,
        total_carryovers=total_carryovers,
        curriculum=curriculum,
        current_topic_name=current_topic_name,
        topic_idx=topic_idx,
        topics_total=topics_total,
        lc_completed=lc_completed,
        interview_summary=interview_summary,
        interviews=interviews,
        race_results=race_results,
    )


@bp.route("/birthdays", methods=["POST"])
def add_birthday():
    name = request.form.get("name", "").strip()
    month_str = request.form.get("month", "").strip()
    day_str = request.form.get("day", "").strip()
    date_str = request.form.get("date", "").strip()
    if not name or not ((month_str and day_str) or date_str):
        flash("Name and date are required.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    try:
        date_str = _normalize_birthday_date(month_str, day_str, date_str)
    except Exception:
        flash("Date must be a valid date.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    birthdays = load_birthdays()
    if any(b.get("name") == name and b.get("date") == date_str for b in birthdays):
        flash("Birthday already exists.", "info")
        return redirect(url_for("main.index", tab="birthdays"))
    birthdays.append({"name": name, "date": date_str})
    save_birthdays(birthdays)
    flash(f"Added birthday for {name}.", "success")
    return redirect(url_for("main.index", tab="birthdays"))


@bp.route("/running/week/<int:week_num>", methods=["GET", "POST"])
def running_week(week_num: int):
    today = date.today()
    plan = load_plan()
    running = plan.get("running", {})
    active_plan = running.get("active") if isinstance(running, dict) else None

    if not active_plan:
        return redirect(url_for("main.index", tab="running"))

    start_date = active_plan["start_date"]

    if request.method == "POST":
        existing_week = plan.get("running", {}).get("active", {}).get("weeks", {}).get(str(week_num), {})
        week_data = {}
        for day in DAYS:
            day_data = {
                "type": request.form.get(f"{day}_type", "rest"),
                "distance_miles": float(request.form.get(f"{day}_distance") or 0),
                "notes": request.form.get(f"{day}_notes", "").strip(),
                "notes_actual": request.form.get(f"{day}_notes_actual", "").strip(),
            }
            if not day_data["notes_actual"]:
                day_data["notes_actual"] = existing_week.get(day, {}).get("notes_actual", "")
            week_data[day] = day_data
        plan["running"]["active"]["weeks"][str(week_num)] = week_data
        _save_plan(plan)
        flash(f"Saved Week {week_num}.", "success")
        return redirect(url_for("main.running_week", week_num=week_num))

    week_data = active_plan.get("weeks", {}).get(str(week_num), {})
    monday = _get_plan_week_monday(start_date, week_num)
    current_plan_week = _get_current_plan_week(start_date, today)

    return render_template(
        "week.html",
        week_num=week_num,
        week_data=week_data,
        monday=monday,
        days=DAYS,
        workout_types=WORKOUT_TYPES,
        today=today,
        is_current_week=(week_num == current_plan_week),
    )


@bp.route("/tap")
def tap():
    try:
        x = int(request.args.get("x", ""))
        y = int(request.args.get("y", ""))
    except (TypeError, ValueError):
        return "Need integer x and y query params", 400
    return handle_tap(x, y) + "\n", 200


@bp.route("/birthdays/update", methods=["POST"])
def update_birthday():
    try:
        idx = int(request.form.get("index", ""))
    except (TypeError, ValueError):
        flash("Invalid index.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    name = request.form.get("name", "").strip()
    month_str = request.form.get("month", "").strip()
    day_str = request.form.get("day", "").strip()
    date_str = request.form.get("date", "").strip()
    if not name or not ((month_str and day_str) or date_str):
        flash("Name and date are required.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    try:
        date_str = _normalize_birthday_date(month_str, day_str, date_str)
    except Exception:
        flash("Date must be a valid date.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    birthdays = _load_sorted_birthdays()
    if not (0 <= idx < len(birthdays)):
        flash("Birthday not found.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    birthdays[idx] = {"name": name, "date": date_str}
    save_birthdays(birthdays)
    flash(f"Updated birthday for {name}.", "success")
    return redirect(url_for("main.index", tab="birthdays"))


@bp.route("/birthdays/delete", methods=["POST"])
def delete_birthday():
    try:
        idx = int(request.form.get("index", ""))
    except (TypeError, ValueError):
        flash("Invalid index.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    birthdays = _load_sorted_birthdays()
    if not (0 <= idx < len(birthdays)):
        flash("Birthday not found.", "error")
        return redirect(url_for("main.index", tab="birthdays"))
    removed = birthdays.pop(idx)
    save_birthdays(birthdays)
    flash(f"Deleted birthday for {removed.get('name')}.", "success")
    return redirect(url_for("main.index", tab="birthdays"))


@bp.route("/running/unarchive-plan", methods=["POST"])
def unarchive_running_plan():
    try:
        idx = int(request.form.get("index", ""))
    except (TypeError, ValueError):
        flash("Invalid plan index.", "error")
        return redirect(url_for("main.index", tab="running"))
    plan = load_plan()
    running = plan.get("running", {})
    if not isinstance(running, dict):
        running = {"active": None, "archived": []}
        plan["running"] = running
    archived = running.get("archived", [])
    if not (0 <= idx < len(archived)):
        flash("Archived plan not found.", "error")
        return redirect(url_for("main.index", tab="running"))
    today = date.today()
    restoring = archived.pop(idx)
    restoring.pop("archived_at", None)
    if running.get("active"):
        existing = running["active"]
        existing["archived_at"] = today.isoformat()
        archived.insert(0, existing)
    running["active"] = restoring
    running["archived"] = archived
    _save_plan(plan)
    flash("Plan restored as active.", "success")
    return redirect(url_for("main.index", tab="running"))


@bp.route("/running/archive-plan", methods=["POST"])
def archive_running_plan():
    plan = load_plan()
    running = plan.get("running", {})
    if isinstance(running, dict) and running.get("active"):
        active = running["active"]
        active["archived_at"] = date.today().isoformat()
        running.setdefault("archived", []).insert(0, active)
        running["active"] = None
        plan["running"] = running
        _save_plan(plan)
        flash("Plan archived.", "success")
    return redirect(url_for("main.index", tab="running"))


@bp.route("/running/intake-questions", methods=["POST"])
def running_intake_questions():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    intake = {
        "race_name": request.form.get("race_name", "").strip(),
        "race_date": request.form.get("race_date", "").strip(),
        "race_miles": request.form.get("race_miles", "").strip(),
        "race_distance_unit": request.form.get("race_distance_unit", "miles").strip(),
        "days_per_week": request.form.get("days_per_week", "4").strip(),
        "current_weekly_mileage": request.form.get("current_weekly_mileage", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "recent_race_result": request.form.get("recent_race_result", "").strip(),
        "start_date": date.today().isoformat(),
    }
    try:
        from integrations.running_claude_api import generate_intake_questions
        questions = generate_intake_questions(intake)
        return jsonify({"questions": questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/running/generate-full-plan", methods=["POST"])
def generate_running_full_plan():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    intake = {
        "race_name": request.form.get("race_name", "").strip(),
        "race_date": request.form.get("race_date", "").strip(),
        "race_miles": request.form.get("race_miles", "").strip(),
        "race_distance_unit": request.form.get("race_distance_unit", "miles").strip(),
        "days_per_week": request.form.get("days_per_week", "4").strip(),
        "current_weekly_mileage": request.form.get("current_weekly_mileage", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "recent_race_result": request.form.get("recent_race_result", "").strip(),
        "qa_context": request.form.get("qa_context", "").strip(),
        "start_date": date.today().isoformat(),
    }
    job_id = job_store.create("running-full")
    thread = threading.Thread(
        target=_running_generate_full_thread,
        args=(job_id, intake),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@bp.route("/running/week-compliance")
def running_week_compliance():
    plan = load_plan()
    running = plan.get("running", {})
    active_plan = running.get("active") if isinstance(running, dict) else None
    if not active_plan:
        return jsonify({"has_data": False})
    today = date.today()
    start_date = active_plan["start_date"]
    week_num = _get_current_plan_week(start_date, today)
    week_monday = _get_plan_week_monday(start_date, week_num)
    week_data = active_plan.get("weeks", {}).get(str(week_num), {})
    if not week_data:
        return jsonify({"has_data": False})
    try:
        from integrations.intervals_api import analyze_week_compliance
        return jsonify(analyze_week_compliance(week_data, week_monday, active_plan.get("start_date", "")))
    except Exception as e:
        return jsonify({"has_data": False, "error": str(e)})


@bp.route("/running/generate-full-plan/status")
def generate_running_full_plan_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/running/coach", methods=["POST"])
def running_coach():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    user_message = request.form.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Message is required."}), 400
    job_id = job_store.create("running-coach")
    thread = threading.Thread(
        target=_running_coach_thread,
        args=(job_id, user_message),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@bp.route("/running/coach/status")
def running_coach_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/running/race-results", methods=["POST"])
def add_race_result():
    from utils.race_results import add_race_result as _add
    try:
        distance = float(request.form.get("distance_miles") or 0)
    except (TypeError, ValueError):
        distance = 0
    _add({
        "date": request.form.get("date", "").strip(),
        "race_name": request.form.get("race_name", "").strip(),
        "distance_miles": distance,
        "finish_time": request.form.get("finish_time", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    })
    return redirect(url_for("main.index", tab="running"))


@bp.route("/running/race-results/delete", methods=["POST"])
def delete_race_result():
    from utils.race_results import delete_race_result as _delete
    _delete(request.form.get("id", ""))
    return redirect(url_for("main.index", tab="running"))


@bp.route("/running/generate-ai", methods=["POST"])
def generate_running_ai():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    try:
        week_num = int(request.form.get("week_num", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "week_num is required."}), 400
    custom_prompt = request.form.get("custom_prompt", "").strip()
    job_id = job_store.create(f"running-week-{week_num}")
    thread = threading.Thread(
        target=_running_generate_thread,
        args=(job_id, week_num, custom_prompt),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "week_num": week_num})


@bp.route("/running/generate-ai/status")
def generate_running_ai_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/interview/coach", methods=["POST"])
def interview_coach():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    week_label = request.form.get("week_label") or get_week_label(date.today())
    user_message = request.form.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Message is required."}), 400
    job_id = job_store.create(f"coach-{week_label}")
    thread = threading.Thread(target=_coach_thread, args=(job_id, week_label, user_message), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@bp.route("/interview/coach/status")
def interview_coach_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/interview/intake-questions", methods=["POST"])
def interview_intake_questions():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    intake = {
        "target_roles": request.form.get("target_roles", "").strip(),
        "target_companies": request.form.get("target_companies", "").strip(),
        "interview_timeline": request.form.get("interview_timeline", "").strip(),
        "current_level": request.form.get("current_level", "").strip(),
        "weekly_hours": request.form.get("weekly_hours", "").strip(),
        "current_strengths": request.form.get("current_strengths", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    try:
        from integrations.curriculum_claude_api import generate_curriculum_questions
        questions = generate_curriculum_questions(intake)
        return jsonify({"questions": questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/interview/generate-curriculum", methods=["POST"])
def generate_interview_curriculum():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    intake = {
        "target_roles": request.form.get("target_roles", "").strip(),
        "target_companies": request.form.get("target_companies", "").strip(),
        "interview_timeline": request.form.get("interview_timeline", "").strip(),
        "current_level": request.form.get("current_level", "").strip(),
        "weekly_hours": request.form.get("weekly_hours", "").strip(),
        "current_strengths": request.form.get("current_strengths", "").strip(),
        "qa_context": request.form.get("qa_context", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    job_id = job_store.create("curriculum")
    thread = threading.Thread(target=_curriculum_generate_thread, args=(job_id, intake), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@bp.route("/interview/generate-curriculum/status")
def generate_interview_curriculum_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/interview/generate-ai", methods=["POST"])
def generate_interview_prep_ai():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set. Add it to your .env file."}), 400

    week_label = request.form.get("week_label") or get_week_label(date.today())

    curriculum_path = Config.DATA_DIR / "curriculum.json"
    if not curriculum_path.exists():
        return jsonify({"error": "curriculum.json not found in data/."}), 400
    curriculum = json.loads(curriculum_path.read_text())

    intensity = request.form.get("intensity", "normal").strip().lower()
    if intensity not in ("light", "normal", "intense"):
        intensity = "normal"
    custom_prompt = request.form.get("custom_prompt", "").strip()

    job_id = job_store.create(week_label)
    thread = threading.Thread(
        target=_claude_generate_thread,
        args=(job_id, week_label, curriculum, intensity, custom_prompt),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "week_label": week_label})


@bp.route("/interview/generate-ai/status")
def generate_interview_prep_ai_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/interview/week/<week_label>")
def interview_week(week_label: str):
    today = date.today()
    current_week = get_week_label(today)
    plan = load_plan()
    monday = get_week_monday(week_label)
    sunday = monday + timedelta(days=6)
    interview_tasks = plan.get("interview_prep", {}).get(week_label, {})
    return render_template(
        "interview_week.html",
        week_label=week_label,
        interview_tasks=interview_tasks,
        monday=monday,
        sunday=sunday,
        days=DAYS,
        today=today,
        current_week=current_week,
        is_past=(week_label < current_week),
        timedelta=timedelta,
        get_week_monday=get_week_monday,
    )


@bp.route("/interview/task", methods=["POST"])
def interview_task():
    action = request.form.get("action", "add")
    week_label = request.form.get("week_label") or get_week_label(date.today())
    day = request.form.get("day", "").strip().lower()
    type_ = request.form.get("type", "other").strip()
    task_text = request.form.get("task", "").strip()
    leetcode_slug = request.form.get("leetcode_slug", "").strip()

    if day not in DAYS:
        flash("Please select a valid day.", "error")
        return _interview_redirect(week_label)

    plan = load_plan()
    interview = plan.setdefault("interview_prep", {})
    week_tasks = interview.setdefault(week_label, {})
    day_tasks = week_tasks.setdefault(day, [])

    if action == "add":
        if not task_text:
            flash("Task text is required.", "error")
            return _interview_redirect(week_label)
        new_task: dict = {"type": type_ or "other", "task": task_text, "completed": False}
        if leetcode_slug:
            new_task["leetcode_slug"] = leetcode_slug
        day_tasks.append(new_task)
        _save_plan(plan)
        flash("Added interview prep task.", "success")
        return _interview_redirect(week_label)

    try:
        idx = int(request.form.get("idx", ""))
    except (TypeError, ValueError):
        flash("Invalid task index.", "error")
        return _interview_redirect(week_label)

    if not (0 <= idx < len(day_tasks)):
        flash("Interview prep task not found.", "error")
        return _interview_redirect(week_label)

    if action == "update":
        if not task_text:
            flash("Task text is required.", "error")
            return _interview_redirect(week_label)
        completed = day_tasks[idx].get("completed", False)
        carryover_from = day_tasks[idx].get("carryover_from")
        day_tasks[idx] = {"type": type_ or "other", "task": task_text, "completed": completed}
        if leetcode_slug:
            day_tasks[idx]["leetcode_slug"] = leetcode_slug
        if carryover_from:
            day_tasks[idx]["carryover_from"] = carryover_from
        _save_plan(plan)
        flash("Updated interview prep task.", "success")
        return _interview_redirect(week_label)

    if action == "delete":
        removed = day_tasks.pop(idx)
        if not day_tasks:
            week_tasks.pop(day, None)
        if not week_tasks:
            interview.pop(week_label, None)
        _save_plan(plan)
        flash(f"Deleted task: {removed.get('task')}", "success")
        return _interview_redirect(week_label)

    if action == "complete":
        day_tasks[idx]["completed"] = not day_tasks[idx].get("completed", False)
        _save_plan(plan)
        return _interview_redirect(week_label)

    flash("Unknown interview prep action.", "error")
    return _interview_redirect(week_label)


@bp.route("/interview/outcomes", methods=["POST"])
def add_interview_outcome():
    from utils.interviews import add_interview
    entry = {
        "date": request.form.get("date", "").strip(),
        "company": request.form.get("company", "").strip(),
        "round_type": request.form.get("round_type", "").strip(),
        "result": request.form.get("result", "pending").strip(),
        "topics": request.form.get("topics", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    if not entry["company"] or not entry["date"]:
        flash("Company and date are required.", "error")
        return redirect(url_for("main.index", tab="interview"))
    add_interview(entry)
    flash("Interview outcome logged.", "success")
    return redirect(url_for("main.index", tab="interview"))


@bp.route("/interview/outcomes/delete", methods=["POST"])
def delete_interview_outcome():
    from utils.interviews import delete_interview
    interview_id = request.form.get("id", "").strip()
    delete_interview(interview_id)
    flash("Interview outcome deleted.", "success")
    return redirect(url_for("main.index", tab="interview"))


@bp.route("/interview/toggle-completion", methods=["POST"])
def toggle_completion():
    data = request.get_json() or {}
    try:
        task_date = date.fromisoformat(data["date"])
        task_name = data["task"]
    except (KeyError, ValueError):
        return jsonify({"error": "invalid"}), 400
    from utils.completions import toggle_manual_completion
    new_state = toggle_manual_completion(task_date, task_name)
    return jsonify({"completed": new_state})


@bp.route("/leetcode/lookup")
def leetcode_lookup():
    try:
        number = int(request.args.get("number", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "number is required"}), 400
    try:
        problem = get_problem_by_number(number)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    if not problem:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "title": problem["title"],
        "slug": problem["titleSlug"],
        "task": f"#{problem['questionFrontendId']} {problem['title']}",
    })
