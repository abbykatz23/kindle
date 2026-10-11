import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent


class Config:
    # Paths
    DATA_DIR = BASE_DIR / "data"
    PLAN_FILE = DATA_DIR / "plan.json"
    BIRTHDAYS_FILE = DATA_DIR / "birthdays.json"
    RACE_RESULTS_FILE = DATA_DIR / "race_results.json"
    RUNNING_COACHING_NOTES_FILE = DATA_DIR / "running_coaching_notes.json"
    OUTPUT_IMAGE_PATH = BASE_DIR / "output" / "dashboard.png"

    # Kindle SSH
    KINDLE_HOST: str = os.getenv("KINDLE_HOST", "192.168.0.53")
    KINDLE_USER: str = os.getenv("KINDLE_USER", "root")
    KINDLE_PASSWORD: str = os.getenv("KINDLE_PASSWORD", "")
    KINDLE_IMAGE_PATH: str = os.getenv("KINDLE_IMAGE_PATH", "/tmp/dashboard.png")

    # Claude
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

    # Intervals.icu
    INTERVALS_API_KEY: str = os.getenv("INTERVALS_API_KEY", "")
    INTERVALS_ATHLETE_ID: str = os.getenv("INTERVALS_ATHLETE_ID", "i0")

    # Flask
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Dashboard canvas (Kindle Paperwhite 1 native portrait resolution)
    DASHBOARD_WIDTH: int = 758
    DASHBOARD_HEIGHT: int = 1024
