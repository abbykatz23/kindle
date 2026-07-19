import os
from datetime import date as Date, date, datetime

from flask import Flask

from config import Config
from web.routes import bp


def _datefmt(d: Date, fmt: str) -> str:
    """strftime that handles %-d (day without leading zero) on Windows and Linux."""
    fmt_safe = fmt.replace("%-d", "\x00day\x00").replace("%#d", "\x00day\x00")
    return d.strftime(fmt_safe).replace("\x00day\x00", str(d.day))


def _short_date(s: str) -> str:
    """Convert ISO date string to short display form, e.g. '2026-06-15' → 'Jun 15'."""
    try:
        d = date.fromisoformat(s)
        return f"{d.strftime('%b')} {d.day}"
    except (ValueError, TypeError):
        return s


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = Config.SECRET_KEY
    app.config["DEBUG"] = Config.DEBUG
    app.jinja_env.filters["datefmt"] = _datefmt
    app.jinja_env.filters["short_date"] = _short_date
    app.register_blueprint(bp)

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from apscheduler.schedulers.background import BackgroundScheduler
        from utils.tap_handler import trigger_refresh
        from utils.weekly_generator import run_running_compliance_check
        scheduler = BackgroundScheduler()
        scheduler.add_job(run_running_compliance_check, trigger="cron", hour=1, minute=5, id="running_compliance")
        # next_run_time=now: fire once immediately on startup (not just 30 min later),
        # so a reboot after a power outage gets a fresh push to the Kindle right away.
        scheduler.add_job(
            trigger_refresh, trigger="interval", minutes=30, id="dashboard_refresh",
            next_run_time=datetime.now(),
        )
        scheduler.start()

    return app
