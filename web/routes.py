import json
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from config import Config
from utils.plan import get_week_label, get_week_monday, load_plan

bp = Blueprint("main", __name__)

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WORKOUT_TYPES = ["easy", "workout", "long", "rest", "race", "other"]


def _save_plan(plan: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.PLAN_FILE.write_text(json.dumps(plan, indent=2))


@bp.route("/")
def index():
    today = date.today()
    current_week = get_week_label(today)
    weeks = [get_week_label(today + timedelta(weeks=i)) for i in range(9)]
    plan = load_plan()

    cutoff = get_week_label(today - timedelta(weeks=4))
    archive_weeks = sorted(
        [w for w in plan.get("running", {}) if w < cutoff],
        reverse=True,
    )

    return render_template(
        "index.html",
        current_week=current_week,
        weeks=weeks,
        plan=plan,
        archive_weeks=archive_weeks,
        days=DAYS,
        workout_types=WORKOUT_TYPES,
        today=today,
        timedelta=timedelta,
        get_week_monday=get_week_monday,
    )


@bp.route("/week/<week_label>", methods=["GET", "POST"])
def week(week_label: str):
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
    )
