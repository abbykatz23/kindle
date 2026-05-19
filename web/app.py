from datetime import date as Date

from flask import Flask

from config import Config
from web.routes import bp


def _datefmt(d: Date, fmt: str) -> str:
    """strftime that handles %-d (day without leading zero) on Windows and Linux."""
    fmt_safe = fmt.replace("%-d", "\x00day\x00").replace("%#d", "\x00day\x00")
    return d.strftime(fmt_safe).replace("\x00day\x00", str(d.day))


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = Config.SECRET_KEY
    app.config["DEBUG"] = Config.DEBUG
    app.jinja_env.filters["datefmt"] = _datefmt
    app.register_blueprint(bp)
    return app
