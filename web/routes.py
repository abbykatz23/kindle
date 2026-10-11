import json
import threading
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from config import Config
from utils import jobs as job_store
from utils.plan import load_plan, load_birthdays, save_birthdays
from utils.privacy import mask_birthdays
from utils.running_mode import VALID_MODES as RUNNING_MODES, get_running_mode, set_running_mode
from utils.tap_handler import _safe_refresh, handle_tap
from web.access import is_owner

bp = Blueprint("main", __name__)

# GET endpoints that still change state (or are edit pages), so public visitors can't use them.
_OWNER_ONLY_GET_ENDPOINTS = {"main.tap", "main.running_week"}


@bp.before_request
def _enforce_public_read_only():
    """Public visitors get a read-only site: every write (and state-changing GET) is refused
    here, server-side, so greyed-out buttons in the UI aren't the only line of defence."""
    g.is_owner = is_owner()
    if g.is_owner:
        return None
    if request.method not in ("GET", "HEAD") or request.endpoint in _OWNER_ONLY_GET_ENDPOINTS:
        abort(403)
    return None


@bp.app_context_processor
def _inject_viewer():
    return {"is_public": not g.get("is_owner", False)}

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
            "goal_time": intake.get("goal_time", ""),
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


@bp.route("/")
def index():
    today = date.today()
    plan = load_plan()
    birthdays = _load_sorted_birthdays()
    if not g.is_owner:
        birthdays = mask_birthdays(birthdays)

    default_tab = (request.args.get("tab") or "running").lower()
    if default_tab not in ("running", "birthdays", "kindle"):
        default_tab = "running"

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

    from utils.race_results import load_race_results
    race_results = load_race_results()

    return render_template(
        "index.html",
        plan=plan,
        birthdays=birthdays,
        default_tab=default_tab,
        days=DAYS,
        workout_types=WORKOUT_TYPES,
        today=today,
        timedelta=timedelta,
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
        race_results=race_results,
        running_mode=get_running_mode(),
        dashboard_width=Config.DASHBOARD_WIDTH,
        dashboard_height=Config.DASHBOARD_HEIGHT,
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


@bp.route("/kindle/image")
def kindle_image():
    # Public visitors get the copy rendered with birthday names masked (see main.py); if it
    # doesn't exist yet, 404 rather than fall back to the unmasked image.
    path = Config.OUTPUT_IMAGE_PATH if g.is_owner else Config.PUBLIC_OUTPUT_IMAGE_PATH
    if not path.exists():
        abort(404)
    response = send_file(path, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@bp.route("/tap")
def tap():
    try:
        x = int(request.args.get("x", ""))
        y = int(request.args.get("y", ""))
    except (TypeError, ValueError):
        return "Need integer x and y query params", 400
    return handle_tap(x, y) + "\n", 200


@bp.route("/running/kindle-mode", methods=["POST"])
def set_kindle_running_mode():
    """Switch the Kindle's RUNNING section between the plan and the last run, then re-render."""
    mode = request.form.get("mode", "")
    if mode not in RUNNING_MODES:
        flash("Unknown running display mode.", "error")
    elif mode != get_running_mode():
        set_running_mode(mode)
        _safe_refresh()
    return redirect(url_for("main.index", tab=request.form.get("tab") or "running"))


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
        "goal_time": request.form.get("goal_time", "").strip(),
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
        "goal_time": request.form.get("goal_time", "").strip(),
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


@bp.route("/running/day-detail/<iso_date>")
def running_day_detail(iso_date):
    """Web-UI-only: full info for a single day — planned run, post-run notes, and (if the
    day has passed) the actual logged run and today's cached coaching note, if any."""
    try:
        day_date = date.fromisoformat(iso_date)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400

    plan = load_plan()
    active_plan = (plan.get("running") or {}).get("active")
    if not active_plan:
        return jsonify({"error": "no active plan"}), 404

    start_date = active_plan.get("start_date")
    start_dt = date.fromisoformat(start_date)
    start_monday = start_dt - timedelta(days=start_dt.weekday())
    week_num = ((day_date - start_monday).days // 7) + 1
    if week_num < 1:
        return jsonify({"error": "date is before the plan's start"}), 404

    week_data = active_plan.get("weeks", {}).get(str(week_num), {})
    day_name = day_date.strftime("%A").lower()
    day_plan = week_data.get(day_name, {})

    result = {
        "date": iso_date,
        "day_name": day_date.strftime("%A"),
        "week_num": week_num,
        "type": day_plan.get("type", "rest"),
        "distance_miles": day_plan.get("distance_miles", 0),
        "notes": day_plan.get("notes", ""),
        "notes_actual": day_plan.get("notes_actual", ""),
        "actual": None,
        "feedback": None,
    }

    today = date.today()
    if day_date <= today:
        try:
            from integrations.intervals_api import get_run_detail_for_date
            actual = get_run_detail_for_date(day_date)
            if actual:
                result["actual"] = {
                    "distance_miles": actual["distance_miles"],
                    "pace_per_mile": actual["pace_per_mile"],
                    "moving_time_s": actual["moving_time_s"],
                }
        except Exception:
            pass

        if day_date == today:
            from utils.run_feedback import load_todays_feedback
            result["feedback"] = load_todays_feedback(today)

    return jsonify(result)


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
