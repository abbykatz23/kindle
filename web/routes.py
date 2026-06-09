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


def _save_plan(plan: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.PLAN_FILE.write_text(json.dumps(plan, indent=2))


def _load_sorted_birthdays() -> list[dict]:
    return sorted(load_birthdays(), key=lambda b: b.get("date", ""))


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


def _running_generate_thread(job_id: str, week_label: str, intensity: str, custom_prompt: str) -> None:
    try:
        from integrations.running_claude_api import edit_weekly_running_plan
        plan = load_plan()
        running_profile = {}
        rp_path = Config.DATA_DIR / "running_profile.json"
        if rp_path.exists():
            running_profile = json.loads(rp_path.read_text())
        result = edit_weekly_running_plan(
            week_label=week_label,
            plan=plan,
            profile=running_profile,
            custom_prompt=custom_prompt,
        )
        fresh_plan = load_plan()
        fresh_plan.setdefault("running", {})[week_label] = result
        _save_plan(fresh_plan)
        job_store.mark_done(job_id)
    except Exception as e:
        job_store.mark_failed(job_id, str(e))


def _running_generate_full_thread(job_id: str, custom_prompt: str) -> None:
    try:
        from integrations.running_claude_api import generate_full_running_plan
        plan = load_plan()
        running_profile = {}
        rp_path = Config.DATA_DIR / "running_profile.json"
        if rp_path.exists():
            running_profile = json.loads(rp_path.read_text())
        weeks_data = generate_full_running_plan(
            plan=plan,
            profile=running_profile,
            custom_prompt=custom_prompt,
        )
        fresh_plan = load_plan()
        fresh_plan.setdefault("running", {}).update(weeks_data)
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

    # Load running profile for race date and future weeks computation
    running_profile: dict = {}
    rp_path = Config.DATA_DIR / "running_profile.json"
    if rp_path.exists():
        running_profile = json.loads(rp_path.read_text())
    race_date_str = running_profile.get("race_date", "2026-10-10")
    race_date_dt = date.fromisoformat(race_date_str)

    past_weeks = sorted(
        [w for w in plan.get("running", {}) if w < current_week],
        reverse=True,
    )

    interview_past_weeks = sorted(
        [w for w in plan.get("interview_prep", {}) if w < current_week],
        reverse=True,
    )
    interview_week_stats = {
        w: _interview_week_stats(data)
        for w, data in plan.get("interview_prep", {}).items()
    }

    # Future running weeks: next week through race date
    future_weeks = []
    wdt = get_week_monday(current_week) + timedelta(weeks=1)
    while wdt <= race_date_dt:
        future_weeks.append(get_week_label(wdt))
        wdt += timedelta(weeks=1)

    running_has_plan = bool(plan.get("running"))

    return render_template(
        "index.html",
        current_week=current_week,
        future_weeks=future_weeks,
        past_weeks=past_weeks,
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
        running_has_plan=running_has_plan,
        running_profile=running_profile,
        race_date_str=race_date_str,
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


@bp.route("/week/<week_label>", methods=["GET", "POST"])
def week(week_label: str):
    today = date.today()
    current_week_label = get_week_label(today)
    plan = load_plan()
    if request.method == "POST":
        running_week = {
            day: {
                "type": request.form.get(f"{day}_type", "rest"),
                "distance_miles": float(request.form.get(f"{day}_distance") or 0),
                "notes": request.form.get(f"{day}_notes", "").strip(),
            }
            for day in DAYS
        }
        plan.setdefault("running", {})[week_label] = running_week
        _save_plan(plan)
        flash(f"Saved plan for {week_label}.", "success")
        return redirect(url_for("main.week", week_label=week_label))
    return render_template(
        "week.html",
        week_label=week_label,
        week_data=plan.get("running", {}).get(week_label, {}),
        monday=get_week_monday(week_label),
        days=DAYS,
        workout_types=WORKOUT_TYPES,
        today=today,
        current_week_label=current_week_label,
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


@bp.route("/running/generate-full-plan", methods=["POST"])
def generate_running_full_plan():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    custom_prompt = request.form.get("custom_prompt", "").strip()
    job_id = job_store.create("running-full")
    thread = threading.Thread(
        target=_running_generate_full_thread,
        args=(job_id, custom_prompt),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@bp.route("/running/generate-full-plan/status")
def generate_running_full_plan_status():
    job_id = request.args.get("job_id", "")
    job = job_store.get_job(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)


@bp.route("/running/generate-ai", methods=["POST"])
def generate_running_ai():
    if not Config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set."}), 400
    week_label = request.form.get("week_label") or get_week_label(date.today())
    intensity = request.form.get("intensity", "normal").strip().lower()
    if intensity not in ("light", "normal", "intense"):
        intensity = "normal"
    custom_prompt = request.form.get("custom_prompt", "").strip()
    job_id = job_store.create(week_label)
    thread = threading.Thread(
        target=_running_generate_thread,
        args=(job_id, week_label, intensity, custom_prompt),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "week_label": week_label})


@bp.route("/running/generate-ai/status")
def generate_running_ai_status():
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
        day_tasks[idx] = {"type": type_ or "other", "task": task_text, "completed": completed}
        if leetcode_slug:
            day_tasks[idx]["leetcode_slug"] = leetcode_slug
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
